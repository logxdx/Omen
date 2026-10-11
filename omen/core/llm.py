"""LLM client: streams a chat completion and normalises it for the agent loop.

Small local models are messy, so this layer smooths over the common quirks:
- reasoning arrives either as `reasoning_content` or inline in `<think>` tags;
- tool calls arrive either natively or as text (`<tool_call>{...}</tool_call>`,
  or a bare `{"name": ..., "arguments": ...}` object).

Every stream ends with exactly one `Completion`.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol

from omen.config import ModelConfig


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text as produced by the model


@dataclass
class TextDelta:
    text: str


@dataclass
class ReasoningDelta:
    text: str


@dataclass
class Completion:
    text: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict | None = None


StreamItem = TextDelta | ReasoningDelta | Completion


class LLM(Protocol):
    def stream(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[StreamItem]: ...


# --------------------------------------------------------------------------- #
# Inline tag routing
# --------------------------------------------------------------------------- #

# Tag → channel. Text inside these tags is kept out of the visible answer.
INLINE_TAGS = {"think": "reasoning", "thinking": "reasoning", "tool_call": "tool_call"}


class TagRouter:
    """Splits streamed text into channels by XML-style tags.

    `feed("a<thi")` + `feed("nk>b</think>c")` yields text "a", reasoning "b",
    text "c": tags split across chunks are held back until they resolve.
    """

    def __init__(self, tags: dict[str, str] = INLINE_TAGS):
        self._tags = tags
        self._buf = ""
        self._open: str | None = None  # tag name we're inside of

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self._buf += chunk
        out: list[tuple[str, str]] = []
        while self._buf:
            if self._open is None:
                hit = self._find_open()
                if hit:
                    idx, tag = hit
                    out.append(("text", self._buf[:idx]))
                    self._buf = self._buf[idx + len(tag) + 2 :]
                    self._open = tag
                    continue
                keep = self._partial_suffix([f"<{t}>" for t in self._tags])
            else:
                close = f"</{self._open}>"
                idx = self._buf.find(close)
                if idx >= 0:
                    out.append((self._tags[self._open], self._buf[:idx]))
                    self._buf = self._buf[idx + len(close) :]
                    self._open = None
                    continue
                keep = self._partial_suffix([close])
            channel = "text" if self._open is None else self._tags[self._open]
            cut = len(self._buf) - keep
            out.append((channel, self._buf[:cut]))
            self._buf = self._buf[cut:]
            break
        return [(c, t) for c, t in out if t]

    def flush(self) -> list[tuple[str, str]]:
        channel = "text" if self._open is None else self._tags[self._open]
        rest, self._buf = self._buf, ""
        return [(channel, rest)] if rest else []

    def _find_open(self) -> tuple[int, str] | None:
        hits = [(self._buf.find(f"<{t}>"), t) for t in self._tags]
        hits = [(i, t) for i, t in hits if i >= 0]
        return min(hits) if hits else None

    def _partial_suffix(self, candidates: list[str]) -> int:
        """Length of the longest buffer suffix that could be the start of a candidate tag."""
        longest = max(len(c) for c in candidates) - 1
        for k in range(min(len(self._buf), longest), 0, -1):
            tail = self._buf[-k:]
            if any(c.startswith(tail) for c in candidates):
                return k
        return 0


# --------------------------------------------------------------------------- #
# Text tool-call recovery
# --------------------------------------------------------------------------- #


def _new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:12]}"


def _call_from_obj(obj: object, tool_names: set[str]) -> ToolCall | None:
    if not isinstance(obj, dict) or obj.get("name") not in tool_names:
        return None
    args = obj.get("arguments", obj.get("parameters", {}))
    if not isinstance(args, str):
        args = json.dumps(args)
    return ToolCall(id=_new_call_id(), name=obj["name"], arguments=args)


def parse_text_tool_calls(
    blocks: list[str], text: str, tool_names: set[str]
) -> tuple[list[ToolCall], str]:
    """Recover tool calls a model wrote as text.

    `blocks` are the bodies of `<tool_call>` tags (already removed from `text`).
    If there are none, a reply that is *only* a JSON object naming a known tool
    is treated as a call. Returns (calls, remaining visible text).
    """
    calls = []
    for block in blocks:
        try:
            call = _call_from_obj(json.loads(block.strip()), tool_names)
        except json.JSONDecodeError:
            call = None
        if call:
            calls.append(call)
    if calls or not tool_names:
        return calls, text

    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            call = _call_from_obj(json.loads(stripped), tool_names)
        except json.JSONDecodeError:
            call = None
        if call:
            return [call], ""
    return [], text


# --------------------------------------------------------------------------- #
# LiteLLM client
# --------------------------------------------------------------------------- #


class LiteLLMClient:
    def __init__(self, config: ModelConfig):
        self.config = config

    async def stream(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[StreamItem]:
        import litellm

        litellm.drop_params = True  # silently drop params a backend doesn't support
        litellm.suppress_debug_info = True

        kwargs: dict = dict(
            model=self.config.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            api_base=self.config.base_url,
            api_key=self.config.api_key,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["parallel_tool_calls"] = False
        if self.config.extra_body:
            kwargs["extra_body"] = self.config.extra_body

        response = await litellm.acompletion(**kwargs)
        async for item in assemble(response, {t["function"]["name"] for t in tools}):
            yield item


async def assemble(chunks: AsyncIterator, tool_names: set[str]) -> AsyncIterator[StreamItem]:
    """Turn OpenAI-style streaming chunks into deltas plus one final Completion."""
    router = TagRouter()
    text: list[str] = []
    reasoning: list[str] = []
    blocks: list[str] = []
    slots: dict[int, dict] = {}
    finish_reason = None
    usage = None

    def route(pieces: list[tuple[str, str]]):
        for channel, piece in pieces:
            if channel == "text":
                text.append(piece)
                yield TextDelta(piece)
            elif channel == "reasoning":
                reasoning.append(piece)
                yield ReasoningDelta(piece)
            else:  # tool_call
                blocks.append(piece)

    async for chunk in chunks:
        if getattr(chunk, "usage", None):
            u = chunk.usage
            usage = u.model_dump() if hasattr(u, "model_dump") else dict(u)
        if not getattr(chunk, "choices", None):
            continue
        choice = chunk.choices[0]
        delta = choice.delta

        r = getattr(delta, "reasoning_content", None)
        if r:
            reasoning.append(r)
            yield ReasoningDelta(r)
        if getattr(delta, "content", None):
            for item in route(router.feed(delta.content)):
                yield item
        for tc in getattr(delta, "tool_calls", None) or []:
            index = tc.index if tc.index is not None else len(slots)
            slot = slots.setdefault(index, {"id": None, "name": "", "arguments": ""})
            if tc.id:
                slot["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn and fn.name and not slot["name"]:
                slot["name"] = fn.name
            if fn and fn.arguments:
                slot["arguments"] += fn.arguments
        if choice.finish_reason:
            finish_reason = choice.finish_reason

    for item in route(router.flush()):
        yield item

    calls = [
        ToolCall(id=s["id"] or _new_call_id(), name=s["name"], arguments=s["arguments"] or "{}")
        for _, s in sorted(slots.items())
    ]
    visible = "".join(text)
    if not calls:
        calls, visible = parse_text_tool_calls(blocks, visible, tool_names)

    yield Completion(
        text=visible.strip(),
        reasoning="".join(reasoning).strip(),
        tool_calls=calls,
        finish_reason=finish_reason,
        usage=usage,
    )
