"""Runtime: drives the (forked) Agents SDK and turns its stream into Omen events.

    runtime = Runtime(agent, session)
    async for event in runtime.run("weather in paris?"):
        ...                     # TEXT_MESSAGE_*, TOOL_CALL_*, SUBAGENT_EVENT, ...
    runtime.send("also tokyo")  # while running: injected after the current turn
    runtime.abort()             # stop now

Every frontend (TUI, web, voice) consumes the same events.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from agents import Agent, ItemHelpers, MaxTurnsExceeded, MessageQueue, RunConfig, Runner
from agents.tool_context import ToolContext

from omen.config import MAX_TURNS
from omen.core.events import (
    Custom,
    Event,
    ReasoningContent,
    RunError,
    RunFinished,
    RunStarted,
    StepStarted,
    TextMessageContent,
    TextMessageEnd,
    TextMessageStart,
    ToolCallArgs,
    ToolCallEnd,
    ToolCallResult,
    ToolCallStart,
    SubagentEvent,
    UIComponent,
    UserQuestion,
)
from omen.core.session import CUSTOM_DATA_KEY, Session
from omen.core.tools import ToolResult, classify_error
from omen.ui.components import UIPayload, payload
from omen.ui.extract import strip_hints


async def _no_answer(question: str, options: list[str] | None) -> str:
    raise RuntimeError("no user is available to answer")


@dataclass
class OmenContext:
    """The SDK run context: what tools (delegation, skills, ask_user) can reach."""

    session: Session
    emit: Callable[[Event], None] = field(default=lambda event: None)
    state: dict = field(default_factory=dict)  # persists across runs (loaded skills, ...)
    ask: Callable[[str, list[str] | None], Awaitable[str]] = field(default=_no_answer)


# Text after these never reaches the UI: tool calls written as text (OmenModel turns them into real
# calls) and UI hint tags (omen.ui.extract).
HIDDEN_MARKERS = ("<tool_call>", "<ui:")


class EventMapper:
    """Maps SDK stream events to Omen events (one mapper per run)."""

    def __init__(self) -> None:
        self.step = 0
        self._message_id: str | None = None  # Omen id of the text message being streamed
        self._text = ""  # text of that message so far
        self._emitted = 0  # how much of it has been streamed
        self._streamed_unmatched = 0  # streamed messages not yet matched to message_output_created
        self._tool_names: dict[str, str] = {}

    def map(self, event: Any) -> list[Event]:
        if event.type == "raw_response_event":
            return self._raw(event.data)
        if event.type == "run_item_stream_event":
            return self._item(event.name, event.item)
        if event.type == "agent_updated_stream_event":
            return [Custom("agent", event.new_agent.name)]
        return []

    def _raw(self, data: Any) -> list[Event]:
        kind = getattr(data, "type", "")
        if kind == "response.created":
            self.step += 1
            return [StepStarted(self.step)]
        if kind == "response.output_text.delta":
            out: list[Event] = []
            if self._message_id is None:
                self._message_id = uuid.uuid4().hex[:12]
                self._text, self._emitted = "", 0
                out.append(TextMessageStart(self._message_id))
            self._text += data.delta
            visible = self._visible_until()
            if visible > self._emitted:
                out.append(TextMessageContent(self._message_id, self._text[self._emitted : visible]))
                self._emitted = visible
            return out
        if kind in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
            return [ReasoningContent(self._message_id or "reasoning", data.delta)]
        if kind == "response.output_item.done" and getattr(data.item, "type", None) == "message":
            if self._message_id is not None:
                message_id, self._message_id = self._message_id, None
                self._streamed_unmatched += 1
                out = []
                if not any(m in self._text for m in HIDDEN_MARKERS) and self._emitted < len(self._text):
                    out.append(TextMessageContent(message_id, self._text[self._emitted :]))  # held-back tail
                return out + [TextMessageEnd(message_id, self._text)]
        return []

    def _visible_until(self) -> int:
        """Stream text up to a hidden marker; hold back a tail that could be the start of one."""
        hits = [self._text.find(m) for m in HIDDEN_MARKERS if m in self._text]
        if hits:
            return min(hits)
        for k in range(min(len(self._text), max(len(m) for m in HIDDEN_MARKERS) - 1), 0, -1):
            if any(m.startswith(self._text[-k:]) for m in HIDDEN_MARKERS):
                return len(self._text) - k
        return len(self._text)

    def _item(self, name: str, item: Any) -> list[Event]:
        if name == "tool_called":
            raw = item.raw_item
            call_id = _get(raw, "call_id") or _get(raw, "id") or ""
            tool_name = _get(raw, "name") or ""
            self._tool_names[call_id] = tool_name
            return [
                ToolCallStart(call_id, tool_name),
                ToolCallArgs(call_id, _get(raw, "arguments") or ""),
                ToolCallEnd(call_id),
            ]
        if name == "tool_output":
            raw = item.raw_item
            call_id = _get(raw, "call_id") or ""
            content = str(_get(raw, "output") if _get(raw, "output") is not None else item.output)
            custom = item.custom_data or {}
            ui = payload(custom.get("ui"), text=content[:500])
            return [
                ToolCallResult(
                    call_id,
                    self._tool_names.get(call_id, ""),
                    content,
                    ui.model_dump() if ui else None,
                    custom.get("error") or classify_error(content),
                )
            ]
        if name == "message_output_created":
            if self._streamed_unmatched:
                self._streamed_unmatched -= 1
                return []
            text = ItemHelpers.text_message_output(item)
            visible, _ = strip_hints(text)
            message_id = uuid.uuid4().hex[:12]
            return [
                TextMessageStart(message_id),
                TextMessageContent(message_id, visible),
                TextMessageEnd(message_id, text),
            ]
        if name == "user_message_injected":
            return [Custom("message_injected", _get(item.raw_item, "content"))]
        return []


def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


_DONE = object()
logger = logging.getLogger(__name__)


@dataclass
class _Failure:
    error: BaseException


class Runtime:
    def __init__(
        self,
        agent: Agent,
        session: Session | None = None,
        *,
        max_turns: int = MAX_TURNS,
        run_config: RunConfig | None = None,
        prepare: Callable[[str, dict], list[Event]] | None = None,
        ask_handler: Callable[[str, list[str] | None], Awaitable[str]] | None = None,
        components: Callable[[str, set[str] | None, str], Awaitable[list[UIPayload]]] | None = None,
        ui: set[str] | None = None,
        context: Callable[[str, dict], str | None] | None = None,
    ):
        """
        Args:
            prepare: called with (user message, state) before each run, e.g. the skill
                pre-router; the events it returns are yielded after RUN_STARTED.
            ask_handler: answers `ask_user` questions programmatically (evals, scripts).
                Without it, questions are emitted as USER_QUESTION and wait for `answer()`.
            components: builds UI components from each assistant reply, given (reply, ui, user request)
                (omen.ui.extract.components_for);
                they are emitted as UI_COMPONENT before RUN_FINISHED.
            ui: component types the frontend renders (None = all). Tool results of other
                types lose their details (the text stays) and only these are extracted.
            context: builds a block (time, memories, skill instructions) prepended to each new
                user message, after `prepare`. Keeping varying text here instead of in the system
                prompt is what keeps the model server's prompt cache warm.
        """
        self.agent = agent
        self.session = session or Session()
        self.max_turns = max_turns
        self.run_config = run_config or RunConfig(tracing_disabled=True)
        self.prepare = prepare
        self.ask_handler = ask_handler
        self.components = components
        self.context = context
        self.ui = ui
        self.queue = MessageQueue()
        self.state: dict = {}
        self.running = False
        self._result: Any = None
        self._aborted = False
        self._question: tuple[UserQuestion, asyncio.Future] | None = None
        self._emit: Callable[[Event], None] = lambda event: None

    @classmethod
    def for_assistant(cls, assistant: Any, session: Session | None = None, **kwargs: Any) -> Runtime:
        """A runtime wired to an omen.assistant.Assistant (agent, skill router, context block)."""
        runtime = cls(assistant.agent, session, **kwargs)
        runtime.attach(assistant)
        return runtime

    def attach(self, assistant: Any) -> None:
        """Switch to another assistant (e.g. persona change) keeping the session and state."""
        self.agent = assistant.agent
        self.prepare = assistant.prepare
        self.context = assistant.context

    def send(self, text: str) -> None:
        """Queue a user message while a run is in progress (delivered after the current turn)."""
        self.queue.put(text)

    def abort(self) -> None:
        self._aborted = True
        if self._result is not None:
            self._result.cancel(mode="immediate")

    @property
    def pending_question(self) -> UserQuestion | None:
        return self._question[0] if self._question else None

    def answer(self, text: str) -> bool:
        """Answer the pending `ask_user` question. Returns False if nothing is pending."""
        if self._question is None or self._question[1].done():
            return False
        self._question[1].set_result(text)
        return True

    async def _ask(self, question: str, options: list[str] | None) -> str:
        if self.ask_handler is not None:
            return await self.ask_handler(question, options)
        event = UserQuestion(uuid.uuid4().hex[:12], question, options)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._question = (event, future)
        self._emit(event)
        try:
            return await future
        finally:
            self._question = None

    async def _run_pre_call(
        self, call: dict, user_message: str, context: OmenContext, config: RunConfig, out: asyncio.Queue
    ) -> AsyncIterator[Event]:
        """Run a tool call chosen by the harness (not the model) before the model's turn.

        The user message, the call and its result are appended to the session in order, so the
        conversation reads exactly as if the model had made the call (and stays cache-friendly).
        """
        tool = next((t for t in self.agent.tools if getattr(t, "name", None) == call["name"]), None)
        if tool is None:
            return
        await self.session.add_items([{"role": "user", "content": user_message}])
        call_id = f"call_{uuid.uuid4().hex[:16]}"
        arguments = json.dumps(call.get("arguments", {}), ensure_ascii=False)
        yield ToolCallStart(call_id, tool.name)
        yield ToolCallArgs(call_id, arguments)
        yield ToolCallEnd(call_id)
        tool_context = ToolContext(
            context=context, tool_name=tool.name, tool_call_id=call_id, tool_arguments=arguments,
            run_config=config, conversation_history=list(self.session.items()),
        )
        task = asyncio.create_task(tool.on_invoke_tool(tool_context, arguments))
        while not task.done():  # stream what the tool emits (e.g. a persona's run) while it works
            getter = asyncio.ensure_future(out.get())
            done, _ = await asyncio.wait({task, getter}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                yield self._filter_ui(getter.result())
            else:
                getter.cancel()
            if self._aborted and not task.done():
                task.cancel()
        while not out.empty():
            yield self._filter_ui(out.get_nowait())
        try:
            output = task.result()
        except asyncio.CancelledError:
            output = ToolResult("Cancelled: the user stopped the run.", error="aborted")
        except Exception as e:
            output = ToolResult(f"Error in {tool.name}: {type(e).__name__}: {e}", error="exception")
        content = str(output)
        details = output.details if isinstance(output, ToolResult) else None
        error = output.error if isinstance(output, ToolResult) else classify_error(content)
        ui = payload(details, text=content[:500])
        yield self._filter_ui(ToolCallResult(call_id, tool.name, content, ui.model_dump() if ui else None, error))
        result_item: dict = {"type": "function_call_output", "call_id": call_id, "output": content}
        if details is not None:
            result_item[CUSTOM_DATA_KEY] = {"ui": details}
        await self.session.add_items([
            {"type": "function_call", "call_id": call_id, "name": tool.name, "arguments": arguments},
            result_item,
        ])

    def _hint_kinds(self) -> list[str]:
        """Hint tags the model may use: extractor-filled kinds the frontend renders (tables need none)."""
        if self.components is None:
            return []
        return [k for k in ("chart", "card") if self.ui is None or k in self.ui]

    def _filter_ui(self, event: Event) -> Event:
        """Drop tool-result details the frontend can't render (it falls back to the text)."""
        target = event.event if isinstance(event, SubagentEvent) else event
        if (
            self.ui is not None
            and isinstance(target, ToolCallResult)
            and isinstance(target.details, dict)
            and target.details.get("type") not in self.ui
        ):
            target.details = None
        return event

    async def run(self, user_input: str) -> AsyncIterator[Event]:
        run_id = uuid.uuid4().hex[:12]
        self.running = True
        self._aborted = False
        out: asyncio.Queue = asyncio.Queue()
        self._emit = out.put_nowait
        context = OmenContext(session=self.session, emit=out.put_nowait, state=self.state, ask=self._ask)
        config = dataclasses.replace(
            self.run_config,
            message_queue=self.queue,
            tool_not_found_behavior="return_error_to_model",
        )
        yield RunStarted(run_id)
        self.state["user_message"] = user_input
        self.state["ui_hints"] = self._hint_kinds()
        replies: list[tuple[str, str, asyncio.Task]] = []
        for event in self.prepare(user_input, self.state) if self.prepare else []:
            yield event

        reason = "done"
        pre_call = self.state.pop("pre_call", None)  # e.g. a delegation the user asked for by name
        block = self.context(user_input, self.state) if self.context else None
        next_input: str | list[dict] = f"{block}\n\n{user_input}" if block else user_input
        try:
            if pre_call and isinstance(next_input, str):
                async for event in self._run_pre_call(pre_call, next_input, context, config, out):
                    yield event
                next_input = []  # the session now ends with the call's result; the model replies to it
            while not self._aborted:
                result = Runner.run_streamed(
                    self.agent,
                    next_input,
                    context=context,
                    max_turns=self.max_turns,
                    run_config=config,
                    session=self.session,
                )
                self._result = result
                mapper = EventMapper()

                async def pump(result=result, mapper=mapper) -> None:
                    try:
                        async for sdk_event in result.stream_events():
                            for event in mapper.map(sdk_event):
                                out.put_nowait(event)
                    except BaseException as e:  # surfaced to the consumer below
                        out.put_nowait(_Failure(e))
                    finally:
                        out.put_nowait(_DONE)

                task = asyncio.create_task(pump())
                while (event := await out.get()) is not _DONE:
                    if isinstance(event, _Failure):
                        if isinstance(event.error, asyncio.CancelledError) and self._aborted:
                            continue  # abort() cancelled the SDK run; finish below
                        raise event.error
                    event = self._filter_ui(event)
                    if isinstance(event, TextMessageEnd) and self.components and event.text.strip():
                        request = self.state.get("user_message", "")
                        extraction = asyncio.create_task(self.components(event.text, self.ui, request))
                        replies.append((event.message_id, event.text, extraction))
                    yield event
                await task
                usage = result.context_wrapper.usage
                yield Custom("usage", {
                    "requests": usage.requests,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                    "cached_tokens": getattr(usage.input_tokens_details, "cached_tokens", 0) or 0,
                })

                if self._aborted:
                    reason = "aborted"
                    break
                pending = self.queue.drain()  # arrived after the run's last injection point
                if not pending:
                    break
                for text in pending:
                    yield Custom("message_injected", text)
                next_input = [{"role": "user", "content": text} for text in pending]
            if self._aborted:
                reason = "aborted"
        except MaxTurnsExceeded:
            reason = "max_turns"
        except Exception as e:
            reason = "error"
            yield RunError(run_id, f"{type(e).__name__}: {e}")
        finally:
            self.running = False
            self._result = None

        for message_id, text, extraction in replies:
            try:
                for component in await extraction:
                    self.session.add_reply_component(text, component.model_dump())  # for re-rendering history
                    yield UIComponent(message_id, component.model_dump())
            except Exception:  # a failed extraction never fails the run
                logger.exception("component extraction failed")

        yield RunFinished(run_id, reason)
