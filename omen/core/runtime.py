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
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

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
)
from omen.core.session import Session
from omen.core.tools import classify_error


@dataclass
class OmenContext:
    """The SDK run context: what tools (e.g. delegation) can reach."""

    session: Session
    emit: Callable[[Event], None] = field(default=lambda event: None)
    state: dict = field(default_factory=dict)


class EventMapper:
    """Maps SDK stream events to Omen events (one mapper per run)."""

    def __init__(self) -> None:
        self.step = 0
        self._message_id: str | None = None  # Omen id of the text message being streamed
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
                out.append(TextMessageStart(self._message_id))
            out.append(TextMessageContent(self._message_id, data.delta))
            return out
        if kind in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
            return [ReasoningContent(self._message_id or "reasoning", data.delta)]
        if kind == "response.output_item.done" and getattr(data.item, "type", None) == "message":
            if self._message_id is not None:
                message_id, self._message_id = self._message_id, None
                self._streamed_unmatched += 1
                return [TextMessageEnd(message_id)]
        return []

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
            return [
                ToolCallResult(
                    call_id,
                    self._tool_names.get(call_id, ""),
                    content,
                    custom.get("ui"),
                    custom.get("error") or classify_error(content),
                )
            ]
        if name == "message_output_created":
            if self._streamed_unmatched:
                self._streamed_unmatched -= 1
                return []
            text = ItemHelpers.text_message_output(item)
            message_id = uuid.uuid4().hex[:12]
            return [TextMessageStart(message_id), TextMessageContent(message_id, text), TextMessageEnd(message_id)]
        if name == "user_message_injected":
            return [Custom("message_injected", _get(item.raw_item, "content"))]
        return []


def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


_DONE = object()


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
    ):
        self.agent = agent
        self.session = session or Session()
        self.max_turns = max_turns
        self.run_config = run_config or RunConfig(tracing_disabled=True)
        self.queue = MessageQueue()
        self.running = False
        self._result: Any = None
        self._aborted = False

    def send(self, text: str) -> None:
        """Queue a user message while a run is in progress (delivered after the current turn)."""
        self.queue.put(text)

    def abort(self) -> None:
        self._aborted = True
        if self._result is not None:
            self._result.cancel(mode="immediate")

    async def run(self, user_input: str) -> AsyncIterator[Event]:
        run_id = uuid.uuid4().hex[:12]
        self.running = True
        self._aborted = False
        out: asyncio.Queue = asyncio.Queue()
        context = OmenContext(session=self.session, emit=out.put_nowait)
        config = dataclasses.replace(
            self.run_config,
            message_queue=self.queue,
            tool_not_found_behavior="return_error_to_model",
        )
        yield RunStarted(run_id)

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

        yield RunFinished(run_id, reason)
