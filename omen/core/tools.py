"""Tools: definition, schema generation, validation and execution.

A tool is a plain Python function with type hints and a Google-style docstring:

    @tool
    def get_weather(city: str, units: str = "celsius") -> str:
        '''Current weather for a city.

        Args:
            city: City name, e.g. "Paris".
            units: "celsius" or "fahrenheit".
        '''

Design rules for small models:
- Nothing the model sends can crash the run. Unknown tools, malformed JSON,
  bad arguments and exceptions all come back as error results it can act on.
- Near-miss tool names (`getWeather`, `functions.get_weather`) are resolved.
- What the model sees (`content`) is capped; rich data for the UI goes in `details`.
"""

from __future__ import annotations

import asyncio
import difflib
import inspect
import json
import re
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from omen.config import TOOL_CONTENT_MAX_CHARS


@dataclass
class ToolResult:
    content: str  # shown to the model
    details: Any = None  # rendered by the UI, never sent to the model
    error: str | None = None  # "unknown_tool" | "invalid_args" | "exception" | "loop" | "aborted"

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass
class ToolContext:
    """Injected into tools that declare a `ctx: ToolContext` parameter (hidden from the model)."""

    registry: ToolRegistry
    agent: Any = None
    session: Any = None
    state: dict = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable
    params: type[BaseModel]
    ctx_param: str | None = None
    max_chars: int = TOOL_CONTENT_MAX_CHARS

    def schema(self) -> dict:
        """OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _clean_schema(self.params.model_json_schema()),
            },
        }

    def signature(self) -> str:
        """Compact parameter list for error messages, e.g. `city (string), units (string, optional)`."""
        props = self.schema()["function"]["parameters"].get("properties", {})
        required = set(self.schema()["function"]["parameters"].get("required", []))
        parts = []
        for name, spec in props.items():
            kind = spec.get("type", "any")
            parts.append(f"{name} ({kind})" if name in required else f"{name} ({kind}, optional)")
        return ", ".join(parts) or "no parameters"


# --------------------------------------------------------------------------- #
# @tool decorator
# --------------------------------------------------------------------------- #


def tool(fn: Callable | None = None, *, name: str | None = None, max_chars: int | None = None):
    """Turn a typed, documented function into a Tool."""

    def build(f: Callable) -> Tool:
        description, arg_docs = _parse_docstring(inspect.getdoc(f) or "")
        hints = typing.get_type_hints(f)
        fields: dict[str, Any] = {}
        ctx_param = None
        for pname, param in inspect.signature(f).parameters.items():
            annotation = hints.get(pname, str)
            if annotation is ToolContext:
                ctx_param = pname
                continue
            default = ... if param.default is inspect.Parameter.empty else param.default
            fields[pname] = (annotation, Field(default, description=arg_docs.get(pname)))
        tool_name = name or f.__name__
        params = create_model(
            f"{tool_name}_args", __config__=ConfigDict(extra="ignore"), **fields
        )
        return Tool(
            name=tool_name,
            description=description or tool_name,
            fn=f,
            params=params,
            ctx_param=ctx_param,
            max_chars=max_chars or TOOL_CONTENT_MAX_CHARS,
        )

    return build(fn) if fn is not None else build


def _parse_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Split a Google-style docstring into (description, {arg: description})."""
    description: list[str] = []
    args: dict[str, str] = {}
    section = "description"
    current = None
    for line in doc.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"(Args|Arguments|Parameters):", stripped):
            section = "args"
            continue
        if re.fullmatch(r"(Returns|Raises|Yields|Examples?):", stripped):
            section = "other"
            continue
        if section == "description":
            description.append(stripped)
        elif section == "args" and stripped:
            m = re.match(r"^(\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)$", stripped)
            if m:
                current = m.group(1)
                args[current] = m.group(2)
            elif current:
                args[current] += " " + stripped
    text = " ".join(" ".join(description).split())
    return text, args


def _clean_schema(schema: Any) -> Any:
    """Drop noise small models don't need: titles, and `anyOf [X, null]` → X."""
    if isinstance(schema, dict):
        any_of = schema.get("anyOf")
        if isinstance(any_of, list):
            non_null = [s for s in any_of if s.get("type") != "null"]
            if len(non_null) == 1 and len(any_of) == 2:
                merged = {k: v for k, v in schema.items() if k != "anyOf"}
                merged.update(non_null[0])
                schema = merged
        return {k: _clean_schema(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_clean_schema(s) for s in schema]
    return schema


# --------------------------------------------------------------------------- #
# Registry and execution
# --------------------------------------------------------------------------- #


def _normalise(name: str) -> str:
    name = name.strip().split(".")[-1]  # "functions.get_weather" → "get_weather"
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)  # camelCase → snake_case
    return name.replace("-", "_").replace(" ", "_").lower()


class ToolRegistry:
    """All known tools, plus which of them the model can currently see."""

    def __init__(self, tools: list[Tool] = ()):
        self._tools: dict[str, Tool] = {}
        self._visible: dict[str, None] = {}  # ordered set
        for t in tools:
            self.add(t)

    def add(self, t: Tool, visible: bool = True) -> None:
        self._tools[t.name] = t
        if visible:
            self._visible[t.name] = None

    def show(self, *names: str) -> None:
        for n in names:
            if n in self._tools:
                self._visible[n] = None

    def hide(self, *names: str) -> None:
        for n in names:
            self._visible.pop(n, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def visible(self) -> list[Tool]:
        return [self._tools[n] for n in self._visible]

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.visible]

    def resolve(self, name: str) -> Tool | None:
        """Find a visible tool by exact, normalised or close-enough name."""
        if name in self._visible:
            return self._tools[name]
        by_norm = {_normalise(n): n for n in self._visible}
        norm = _normalise(name)
        if norm in by_norm:
            return self._tools[by_norm[norm]]
        close = difflib.get_close_matches(norm, list(by_norm), n=1, cutoff=0.8)
        return self._tools[by_norm[close[0]]] if close else None

    async def execute(self, name: str, arguments: str | dict, ctx: ToolContext | None = None) -> tuple[str, ToolResult]:
        """Run a tool call. Returns (resolved tool name, result). Never raises."""
        t = self.resolve(name)
        if t is None:
            available = ", ".join(self._visible) or "none"
            return name, ToolResult(
                f"Error: there is no tool named '{name}'. Available tools: {available}.",
                error="unknown_tool",
            )

        try:
            args = parse_arguments(arguments)
        except ValueError as e:
            return t.name, ToolResult(
                f"Error: could not parse arguments for {t.name}: {e}. "
                f"Send a JSON object with: {t.signature()}.",
                error="invalid_args",
            )
        fields = t.params.model_fields
        for wrapper in ("arguments", "parameters", "args"):
            if set(args) == {wrapper} and isinstance(args[wrapper], dict) and wrapper not in fields:
                args = args[wrapper]

        try:
            validated = t.params.model_validate(args)
        except ValidationError as e:
            return t.name, ToolResult(_format_validation_error(t, e), error="invalid_args")

        kwargs = {k: getattr(validated, k) for k in fields}
        if t.ctx_param:
            kwargs[t.ctx_param] = ctx or ToolContext(registry=self)
        try:
            if inspect.iscoroutinefunction(t.fn):
                raw = await t.fn(**kwargs)
            else:
                raw = await asyncio.to_thread(t.fn, **kwargs)
        except Exception as e:  # tool bugs and expected failures alike go back to the model
            return t.name, ToolResult(f"Error in {t.name}: {type(e).__name__}: {e}", error="exception")

        result = _to_result(raw)
        result.content = truncate(result.content, t.max_chars)
        return t.name, result


def parse_arguments(raw: str | dict) -> dict:
    """Parse model-written JSON arguments, repairing common small-model mistakes."""
    if isinstance(raw, dict):
        return raw
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    if not text:
        return {}
    candidates = [text]
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])
    for c in list(candidates):
        candidates.append(re.sub(r",\s*([}\]])", r"\1", c))  # trailing commas
    for c in candidates:
        try:
            value = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(value, str):  # double-encoded JSON
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        if isinstance(value, dict):
            return value
        raise ValueError("arguments must be a JSON object")
    raise ValueError("invalid JSON")


def _format_validation_error(t: Tool, e: ValidationError) -> str:
    lines = [f"Error: invalid arguments for {t.name}:"]
    for err in e.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(arguments)"
        lines.append(f"- {loc}: {err['msg']}")
    lines.append(f"Expected: {t.signature()}.")
    return "\n".join(lines)


def _to_result(raw: Any) -> ToolResult:
    if isinstance(raw, ToolResult):
        return raw
    if raw is None:
        return ToolResult("Done.")
    if isinstance(raw, str):
        return ToolResult(raw)
    if isinstance(raw, BaseModel):
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
