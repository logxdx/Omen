"""A session's current branch as simple messages, for re-rendering a transcript (TUI, web)."""

from __future__ import annotations

import re

from omen.core.session import CUSTOM_DATA_KEY, Session
from omen.ui.components import payload


_CONTEXT = re.compile(r"^\s*<context>.*?</context>\s*", re.DOTALL)


def strip_context(text: str) -> str:
    """A user message without its `<context>` block (time, memories, skill notes)."""
    return _CONTEXT.sub("", text, count=1)


def history(session: Session, entry_id: str | None = None) -> list[dict]:
    """Messages along the current branch (or up to `entry_id`); tool results carry their UI payloads.

    Each message: {"role": "user"|"assistant", "content"} or
    {"role": "tool_call", "id", "name", "arguments"} or
    {"role": "tool", "id", "name", "content", "ui"}.
    """
    out: list[dict] = []
    names: dict[str, str] = {}
    for item in session.items(entry_id):
        if not isinstance(item, dict):
            continue
        role, kind = item.get("role"), item.get("type")
        if role in ("user", "assistant") and kind in (None, "message"):
            content = item.get("content")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if role == "user":
                content = strip_context(content or "")
            out.append({"role": role, "content": content or ""})
        elif kind == "function_call":
            names[item.get("call_id", "")] = item.get("name", "")
            out.append({"role": "tool_call", "id": item.get("call_id"), "name": item.get("name"), "arguments": item.get("arguments")})
        elif kind == "function_call_output":
            ui = payload((item.get(CUSTOM_DATA_KEY) or {}).get("ui"), text=str(item.get("output", ""))[:500])
            out.append({
                "role": "tool", "id": item.get("call_id"), "name": names.get(item.get("call_id", ""), ""),
                "content": item.get("output"), "ui": ui.model_dump() if ui else None,
            })
    return out
