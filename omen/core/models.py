"""Model construction: LiteLLM (Ollama / llama.cpp / OpenAI-compatible) behind the Agents SDK.

`OmenModel` repairs two things small local models do that the SDK can't handle:
- the whole answer lands in the reasoning channel (thinking models that never
  close their think block): the reasoning becomes the visible answer;
- tool calls are written as text (`<tool_call>{json}</tool_call>`, or GLM-style
  `<tool_call>name<arg_key>k</arg_key><arg_value>v</arg_value></tool_call>`)
  instead of native calls: they become real function calls.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, AsyncIterator

from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from omen.config import ModelConfig

_TOOL_CALL = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.DOTALL)
_GLM_ARG = re.compile(r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>", re.DOTALL)
FAKE_ID = "__fake_id__"


def make_model(config: ModelConfig) -> OmenModel:
    return OmenModel(model=config.model, base_url=config.base_url, api_key=config.api_key)


def make_settings(config: ModelConfig) -> ModelSettings:
    return ModelSettings(
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        parallel_tool_calls=False,
        include_usage=True,
        extra_body=config.extra_body or None,
    )


class OmenModel(LitellmModel):
    """LitellmModel + output repair, and one retry when a response comes back empty or with a tool
    call the server could not parse."""

    async def get_response(self, system_instructions, input, model_settings, tools, *args: Any, **kwargs: Any):
        for attempt in range(2):
            try:
                response = await super().get_response(system_instructions, input, model_settings, tools, *args, **kwargs)
            except Exception as e:
                if attempt or not is_bad_tool_call(e):
                    raise
                continue
            response.output = repair_output(list(response.output), _tool_names(tools))
            if attempt or not is_empty(response.output):
                return response
        return response

    async def stream_response(
        self, system_instructions, input, model_settings, tools, *args: Any, **kwargs: Any
    ) -> AsyncIterator[Any]:
        names = _tool_names(tools)
        for attempt in range(2):
            texted = False
            try:
                async for event in super().stream_response(system_instructions, input, model_settings, tools, *args, **kwargs):
                    kind = getattr(event, "type", "")
                    texted = texted or kind == "response.output_text.delta"
                    if kind == "response.completed":
                        event.response.output = repair_output(list(event.response.output), names)
                        if attempt == 0 and is_empty(event.response.output):
                            break  # nothing visible was streamed, so asking again is safe
                        yield event
                        return
                    yield event
            except Exception as e:
                # Tool calls reach the UI only once complete, so a rejected one left nothing on screen.
                if attempt or texted or not is_bad_tool_call(e):
                    raise


def is_bad_tool_call(error: Exception) -> bool:
    """llama.cpp rejected the model's tool call (degenerate or truncated arguments): worth one retry."""
    return "failed to parse tool call" in str(error).lower()


def is_empty(items: list[Any]) -> bool:
    """No visible text and no tool call: the model said nothing at all."""
    for item in items:
        kind = getattr(item, "type", None)
        if kind == "function_call" or (kind == "message" and _message_text(item).strip()):
            return False
    return True


def _tool_names(tools: list[Any]) -> set[str]:
    return {name for t in tools if (name := getattr(t, "name", None))}


def _message_text(item: Any) -> str:
    return "".join(getattr(c, "text", "") or "" for c in getattr(item, "content", []) or [])


def _reasoning_text(item: Any) -> str:
    parts = [getattr(s, "text", "") for s in getattr(item, "summary", []) or []]
    parts += [getattr(c, "text", "") for c in getattr(item, "content", []) or []]
    return "\n".join(p for p in parts if p).strip()


def _message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id=FAKE_ID,
        role="assistant",
        status="completed",
        type="message",
        content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
    )


def parse_text_tool_calls(text: str, tool_names: set[str]) -> tuple[list[ResponseFunctionToolCall], str]:
    """Tool calls written as text → function calls, plus the text that remains."""
    calls = []
    for body in _TOOL_CALL.findall(text):
        body = body.strip()
        name, args = None, {}
        if body.startswith("{"):
            try:
                data = json.loads(body)
                name = data.get("name")
                args = data.get("arguments", data.get("parameters", {}))
            except json.JSONDecodeError:
                continue
        else:
            name = body.split("<", 1)[0].strip()
            args = {k.strip(): v.strip() for k, v in _GLM_ARG.findall(body)}
        if name not in tool_names:
            continue
        calls.append(
            ResponseFunctionToolCall(
                id=FAKE_ID,
                call_id=f"call_{uuid.uuid4().hex[:16]}",
                name=name,
                arguments=args if isinstance(args, str) else json.dumps(args),
                type="function_call",
            )
        )
    remaining = _TOOL_CALL.sub("", text).strip() if calls else text
    return calls, remaining


STUCK_REPLY = "Sorry, I got stuck on that one. Could you ask again, maybe with a bit more detail?"


def is_degenerate(text: str) -> bool:
    """True for text stuck in a repetition loop (few distinct 6-word phrases)."""
    words = text.split()
    if len(words) < 80:
        return False
    shingles = [" ".join(words[i : i + 6]) for i in range(len(words) - 5)]
    return len(set(shingles)) / len(shingles) < 0.3


def repair_output(items: list[Any], tool_names: set[str]) -> list[Any]:
    has_call = any(getattr(i, "type", None) == "function_call" for i in items)
    messages = [i for i in items if getattr(i, "type", None) == "message"]
    text = "".join(_message_text(m) for m in messages)

    if not has_call and is_degenerate(text):
        return [i for i in items if getattr(i, "type", None) != "message"] + [_message(STUCK_REPLY)]

    if not has_call and tool_names and "<tool_call>" in text:
        calls, remaining = parse_text_tool_calls(text, tool_names)
        if calls:
            items = [i for i in items if getattr(i, "type", None) != "message"]
            if remaining:
                items.append(_message(remaining))
            return items + calls

    if not has_call and not text.strip():
        reasoning = "\n".join(_reasoning_text(i) for i in items if getattr(i, "type", None) == "reasoning").strip()
        if reasoning:
            calls, remaining = parse_text_tool_calls(reasoning, tool_names) if "<tool_call>" in reasoning else ([], reasoning)
            if calls:
                return items + calls
            items = [i for i in items if getattr(i, "type", None) != "message"]
            items.append(_message(STUCK_REPLY if is_degenerate(remaining) else remaining))
    return items
