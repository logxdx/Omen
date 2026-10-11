"""Omen tools on top of the Agents SDK's `function_tool`.

A tool is a typed function with a Google-style docstring:

    @tool
    def get_weather(city: str, units: str = "celsius") -> ToolResult:
        '''Current weather for a city.

        Args:
            city: City name, e.g. "Paris".
            units: "celsius" or "fahrenheit".
        '''
        data = ...
        return ToolResult(f"{city}: 18°C", details={"type": "weather", ...})

What `@tool` adds over `function_tool`:
- `ToolResult(content, details)`: the model sees `content` (capped); the UI gets
  `details` on the stream event and in the session (fork patch).
- Exceptions inside the tool become an error result the model can act on.
- Defaulted parameters stay optional (non-strict schema).
- Errors are labelled ("invalid_args", "exception") for the UI and evals.
"""

from __future__ import annotations

import functools
import inspect
import json
from typing import Any, Callable

from agents import FunctionTool, RunContextWrapper, function_tool
from agents.tool import FunctionToolCustomDataContext
from agents.tool_context import ToolContext

from omen.config import TOOL_CONTENT_MAX_CHARS


class ToolResult:
    """Tool output: `content` for the model, `details` for the UI."""

    def __init__(self, content: str, details: Any = None, error: str | None = None):
        self.content = content
        self.details = details
        self.error = error  # "invalid_args" | "exception" | ...

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def __str__(self) -> str:
        return self.content

    def __repr__(self) -> str:
        return f"ToolResult({self.content!r}, details={self.details!r}, error={self.error!r})"


def tool(
    fn: Callable | None = None,
    *,
    name: str | None = None,
    max_chars: int = TOOL_CONTENT_MAX_CHARS,
) -> FunctionTool | Callable[[Callable], FunctionTool]:
    """Turn a typed, documented function into an SDK FunctionTool with Omen conventions."""

    def build(f: Callable) -> FunctionTool:
        tool_name = name or f.__name__

        def finish(raw: Any) -> ToolResult:
            result = _to_result(raw)
            result.content = truncate(result.content, max_chars)
            return result

        def failed(e: Exception) -> ToolResult:
            return ToolResult(f"Error in {tool_name}: {type(e).__name__}: {e}", error="exception")

        if inspect.iscoroutinefunction(f):

            @functools.wraps(f)
            async def wrapper(*args: Any, **kwargs: Any) -> ToolResult:
                try:
                    return finish(await f(*args, **kwargs))
                except Exception as e:
                    return failed(e)

        else:

            @functools.wraps(f)
            def wrapper(*args: Any, **kwargs: Any) -> ToolResult:  # the SDK runs sync tools in a thread
                try:
                    return finish(f(*args, **kwargs))
                except Exception as e:
                    return failed(e)

        return function_tool(
            wrapper,
            name_override=tool_name,
            strict_mode=False,
            custom_data_extractor=extract_custom_data,
            failure_error_function=_invalid_arguments,
        )

    return build(fn) if fn is not None else build


def extract_custom_data(data: FunctionToolCustomDataContext) -> dict[str, Any] | None:
    """Attach `details`/`error` to the SDK output item (never sent to the model)."""
    output = data.output
    if not isinstance(output, ToolResult):
        return None
    custom: dict[str, Any] = {}
    if output.details is not None:
        custom["ui"] = output.details
    if output.error:
        custom["error"] = output.error
    return custom or None


def _invalid_arguments(ctx: RunContextWrapper[Any], error: Exception) -> str:
    """Runs when the SDK can't parse or validate the model's arguments."""
    tool_name = ctx.tool_name if isinstance(ctx, ToolContext) else "the tool"
    return f"Error: invalid arguments for {tool_name}: {error}. Check the parameter names and types."


def classify_error(content: str) -> str | None:
    """Label an error from the model-visible text of a tool output (for outputs without custom data)."""
    if content.startswith("Tool '") and content.endswith("not found."):
        return "unknown_tool"
    if content.startswith("Error: invalid arguments"):
        return "invalid_args"
    if content.startswith("An error occurred while parsing tool arguments"):
        return "invalid_args"
    if content.startswith(("Error", "An error occurred")):
        return "exception"
    return None


def _to_result(raw: Any) -> ToolResult:
    if isinstance(raw, ToolResult):
        return raw
    if raw is None:
        return ToolResult("Done.")
    if isinstance(raw, str):
        return ToolResult(raw)
    if hasattr(raw, "model_dump_json"):
        return ToolResult(raw.model_dump_json())
    return ToolResult(json.dumps(raw, ensure_ascii=False, default=str))


def truncate(text: str, max_chars: int) -> str:
    """Cap text for the model, cutting at a line break when one is near the limit."""
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    newline = head.rfind("\n")
    if newline > max_chars * 0.8:
        head = head[:newline]
    return f"{head}\n[truncated: showing {len(head)} of {len(text)} characters]"
