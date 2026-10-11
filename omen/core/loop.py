"""The agent loop.

One loop, no nesting: stream a completion, run any tool calls in order, feed
the results back, repeat until the model answers without calling a tool.

Guards for small models:
- `max_turns` caps LLM steps per user message;
- a repeated identical tool call gets a nudge instead of running again, and a
  third repeat stops the run;
- every tool call gets a tool message, even on abort, so history stays valid.

Input while running:
- `steer(text)` is injected after the current tool batch (redirects the agent);
- `follow_up(text)` is delivered once the agent would otherwise stop;
- `abort()` stops at the next chunk or tool boundary, keeping partial text.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections import deque
from contextlib import aclosing
from typing import AsyncIterator, Callable

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
from omen.core.llm import LLM, Completion, ReasoningDelta, TextDelta, ToolCall
from omen.core.session import Session
from omen.core.tools import ToolContext, ToolRegistry, ToolResult

LOOP_NUDGE = (
    "You already made this exact call and got the result above. "
    "Use that result, try different arguments, or answer the user."
)


class LoopGuard:
    """Tracks consecutive identical tool calls: 1st runs, 2nd is nudged, 3rd stops the run."""

    def __init__(self):
        self._last: tuple[str, str] | None = None
        self._count = 0

    def check(self, call: ToolCall) -> str:
        try:
            args = json.dumps(json.loads(call.arguments or "{}"), sort_keys=True)
        except json.JSONDecodeError:
            args = call.arguments.strip()
        signature = (call.name, args)
        if signature == self._last:
            self._count += 1
        else:
            self._last, self._count = signature, 1
        return {1: "run", 2: "nudge"}.get(self._count, "stop")


class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: ToolRegistry | None = None,
        system_prompt: str | Callable[[], str] = "",
        session: Session | None = None,
        max_turns: int = MAX_TURNS,
    ):
        self.llm = llm
        self.tools = tools or ToolRegistry()
        self.system_prompt = system_prompt
        self.session = session or Session()
        self.max_turns = max_turns
        self.context = ToolContext(registry=self.tools, agent=self, session=self.session)
        self.running = False
        self._steering: deque[str] = deque()
        self._follow_up: deque[str] = deque()
        self._abort = asyncio.Event()

    # -- control ------------------------------------------------------------ #

    def steer(self, text: str) -> None:
        self._steering.append(text)

    def follow_up(self, text: str) -> None:
        self._follow_up.append(text)

    def abort(self) -> None:
        self._abort.set()

    # -- state -------------------------------------------------------------- #

    @property
    def messages(self) -> list[dict]:
        return self.session.messages()

    def _system(self) -> list[dict]:
        prompt = self.system_prompt() if callable(self.system_prompt) else self.system_prompt
        return [{"role": "system", "content": prompt}] if prompt else []

    def _add(self, message: dict) -> None:
        self.session.add_message(message)

    async def _unless_aborted(self, awaitable) -> tuple[bool, object]:
        """Await `awaitable` unless abort() fires first. Returns (finished, result)."""
        if self._abort.is_set():
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            return False, None
        task = asyncio.ensure_future(awaitable)
        aborted = asyncio.ensure_future(self._abort.wait())
        try:
            done, _ = await asyncio.wait({task, aborted}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            aborted.cancel()
        if task in done:
            return True, task.result()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
            await task
        return False, None

    # -- run ---------------------------------------------------------------- #

    async def run(self, user_input: str) -> AsyncIterator[Event]:
        run_id = uuid.uuid4().hex[:12]
        self._abort.clear()
        self.running = True
        self._add({"role": "user", "content": user_input})
        yield RunStarted(run_id)

        reason = "done"
        guard = LoopGuard()
        try:
            step = 0
            while True:
                if step >= self.max_turns:
                    reason = "max_turns"
                    break
                step += 1
                yield StepStarted(step)

                message_id = uuid.uuid4().hex[:12]
                completion: Completion | None = None
                partial: list[str] = []
                started = False

                stream = self.llm.stream(self._system() + self.messages, self.tools.schemas())
                async with aclosing(stream):
                    while True:
                        try:
                            finished, item = await self._unless_aborted(anext(stream))
                        except StopAsyncIteration:
                            break
                        if not finished:
                            break
                        if isinstance(item, TextDelta):
                            if not started:
                                started = True
                                yield TextMessageStart(message_id)
                            partial.append(item.text)
                            yield TextMessageContent(message_id, item.text)
                        elif isinstance(item, ReasoningDelta):
                            yield ReasoningContent(message_id, item.text)
                        elif isinstance(item, Completion):
                            completion = item
                if started:
                    yield TextMessageEnd(message_id)

                if self._abort.is_set() or completion is None:
                    text = "".join(partial).strip()
                    if text:
                        self._add({"role": "assistant", "content": text})
                    reason = "aborted" if self._abort.is_set() else "error"
                    break

                if completion.usage:
                    yield Custom("usage", completion.usage)

                assistant: dict = {"role": "assistant", "content": completion.text}
                if completion.tool_calls:
                    assistant["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in completion.tool_calls
                    ]
                self._add(assistant)

                if not completion.tool_calls:
                    pending = list(self._steering) + list(self._follow_up)
                    self._steering.clear()
                    self._follow_up.clear()
                    if not pending:
                        break
                    for text in pending:
                        self._add({"role": "user", "content": text})
                    continue

                stop = False
                for call in completion.tool_calls:
                    yield ToolCallStart(call.id, call.name)
                    yield ToolCallArgs(call.id, call.arguments)
                    yield ToolCallEnd(call.id)

                    verdict = guard.check(call)
                    name = call.name
                    if self._abort.is_set():
                        result = ToolResult("Skipped: the user stopped the run.", error="aborted")
                    elif stop or verdict == "stop":
                        result = ToolResult("Stopped: the same call was repeated too many times.", error="loop")
                        stop = True
                    elif verdict == "nudge":
                        result = ToolResult(LOOP_NUDGE, error="loop")
                    else:
                        finished, outcome = await self._unless_aborted(
                            self.tools.execute(call.name, call.arguments, self.context)
                        )
                        if finished:
                            name, result = outcome
                        else:
                            result = ToolResult("Cancelled: the user stopped the run.", error="aborted")

                    yield ToolCallResult(call.id, name, result.content, result.details, result.error)
                    self._add({"role": "tool", "tool_call_id": call.id, "content": result.content})

                if self._abort.is_set():
                    reason = "aborted"
                    break
                if stop:
                    reason = "loop"
                    break
                while self._steering:
                    self._add({"role": "user", "content": self._steering.popleft()})
        except Exception as e:
            reason = "error"
            yield RunError(run_id, f"{type(e).__name__}: {e}")
        finally:
            self.running = False

        yield RunFinished(run_id, reason)
