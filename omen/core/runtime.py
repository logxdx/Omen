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
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from agents import Agent, ItemHelpers, MaxTurnsExceeded, MessageQueue, RunConfig, Runner

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
from omen.core.session import Session
from omen.core.tools import classify_error
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
        components: Callable[[str, set[str] | None], Awaitable[list[UIPayload]]] | None = None,
        ui: set[str] | None = None,
    ):
        """
        Args:
            prepare: called with (user message, state) before each run, e.g. the skill
                pre-router; the events it returns are yielded after RUN_STARTED.
            ask_handler: answers `ask_user` questions programmatically (evals, scripts).
                Without it, questions are emitted as USER_QUESTION and wait for `answer()`.
            components: builds UI components from each assistant reply (omen.ui.extract);
                they are emitted as UI_COMPONENT before RUN_FINISHED.
            ui: component types the frontend renders (None = all). Tool results of other
                types lose their details (the text stays) and only these are extracted.
        """
        self.agent = agent
        self.session = session or Session()
        self.max_turns = max_turns
        self.run_config = run_config or RunConfig(tracing_disabled=True)
        self.prepare = prepare
        self.ask_handler = ask_handler
        self.components = components
        self.ui = ui
        self.queue = MessageQueue()
        self.state: dict = {}
        self.running = False
        self._result: Any = None
        self._aborted = False
        self._question: tuple[UserQuestion, asyncio.Future] | None = None
        self._emit: Callable[[Event], None] = lambda event: None

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
        replies: list[tuple[str, asyncio.Task]] = []
        for event in self.prepare(user_input, self.state) if self.prepare else []:
            yield event

        reason = "done"
        next_input: str | list[dict] = user_input
        try:
            while True:
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
                        replies.append((event.message_id, asyncio.create_task(self.components(event.text, self.ui))))
                    yield event
                await task
                usage = result.context_wrapper.usage
                yield Custom("usage", {
                    "requests": usage.requests,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
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
        except MaxTurnsExceeded:
            reason = "max_turns"
        except Exception as e:
            reason = "error"
            yield RunError(run_id, f"{type(e).__name__}: {e}")
        finally:
            self.running = False
            self._result = None

        for message_id, task in replies:
            try:
                for component in await task:
                    yield UIComponent(message_id, component.model_dump())
            except Exception:  # a failed extraction never fails the run
                logger.exception("component extraction failed")

        yield RunFinished(run_id, reason)
