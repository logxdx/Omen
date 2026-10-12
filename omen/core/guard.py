"""Run guards for small models, applied to every tool (Phase 9).

- Repeat breaker: a tool call identical (name and arguments) to the previous step of the same
  turn is not executed; the model gets a warning with concrete next moves instead. Small models
  loop on the same call far more than large ones.
- Goal reminder: every `every` steps, the tool result ends with "(goal: … · step N of M)", the
  user's request restated where small models attend most. It is stored with the result like any
  tool output, so the prompt stays append-only (an unstored, re-sent tail would cost ling3 ~2,000
  re-evaluated tokens per call; see plan.md Phase 9 and evals/cache_tail.py).

Both read `ToolContext.conversation_history` (fork patch): the model-visible history without the
call being executed.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Any

from agents import FunctionTool

from omen.core.tools import ToolResult

REPEAT_WARNING = (
    "Not run: you just called {name} with these exact arguments and its result is above. "
    "Don't repeat it. Instead: answer the user with what that result says, call a different tool or "
    "use different arguments, or tell the user what is blocking you."
)
REPEAT_AGAIN = (
    "Not run again: this is the same {name} call once more. Stop calling tools now and answer the "
    "user with what you have."
)
_WRAPPERS = re.compile(r"^\s*(<summary>.*?</summary>|<context>.*?</context>)\s*", re.DOTALL)


def _get(item: Any, key: str) -> Any:
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _is_user_message(item: Any) -> bool:
    return _get(item, "role") == "user" and _get(item, "type") in (None, "message")


def _same_args(a: Any, b: Any) -> bool:
    def norm(raw: Any) -> Any:
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return raw

    return norm(a or "{}") == norm(b or "{}")


def _turn(history: list[Any]) -> list[Any]:
    """Items since the last user message (the current turn's steps so far)."""
    for i in range(len(history) - 1, -1, -1):
        if _is_user_message(history[i]):
            return history[i + 1 :]
    return list(history)


def _user_request(history: list[Any]) -> str:
    for item in reversed(history):
        if _is_user_message(item):
            content = _get(item, "content")
            if isinstance(content, list):
                content = " ".join(_get(p, "text") or "" for p in content)
            text = str(content or "")
            while (m := _WRAPPERS.match(text)) is not None:
                text = text[m.end() :]
            text = " ".join(text.split())
            return text if len(text) <= 100 else text[:99].rstrip() + "…"
    return ""


def guarded(tool: FunctionTool, *, max_turns: int, every: int = 5) -> FunctionTool:
    """`tool` with the repeat breaker and the goal reminder."""
    invoke = tool.on_invoke_tool

    async def on_invoke_tool(ctx: Any, arguments: str) -> Any:
        history = list(getattr(ctx, "conversation_history", None) or [])
        turn = _turn(history)
        calls = [i for i in turn if _get(i, "type") == "function_call"]
        if calls and _get(calls[-1], "name") == tool.name and _same_args(_get(calls[-1], "arguments"), arguments):
            last_output = next(
                (str(_get(i, "output") or "") for i in reversed(turn)
                 if _get(i, "type") == "function_call_output" and _get(i, "call_id") == _get(calls[-1], "call_id")),
                "",
            )
            again = last_output.startswith(("Not run:", "Not run again:"))
            return ToolResult((REPEAT_AGAIN if again else REPEAT_WARNING).format(name=tool.name), error="repeat")

        result = await invoke(ctx, arguments)
        step = len(calls) + 1
        if every and step % every == 0 and (goal := _user_request(history)):
            reminder = f"\n\n(goal: {goal} · step {step} of {max_turns})"
            if isinstance(result, ToolResult):
                result = ToolResult(result.content + reminder, details=result.details, error=result.error)
            elif isinstance(result, str):
                result = result + reminder
        return result

    return dataclasses.replace(tool, on_invoke_tool=on_invoke_tool)


def guard_all(tools: list[FunctionTool], *, max_turns: int, every: int = 5) -> list[FunctionTool]:
    return [guarded(t, max_turns=max_turns, every=every) if isinstance(t, FunctionTool) else t for t in tools]
