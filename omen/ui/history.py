"""A session's current branch as simple messages, for re-rendering a transcript (TUI, web)."""

from __future__ import annotations

import re

from omen.core.delegate import RESULT_MARKER, delegation_result
from omen.core.session import CUSTOM_DATA_KEY, Session, message_text
from omen.ui.components import payload
from omen.ui.extract import strip_hints


_CONTEXT = re.compile(r"^\s*<context>.*?</context>\s*", re.DOTALL)


def strip_context(text: str) -> str:
    """A user message without its `<context>` block (time, memories, skill notes)."""
    return _CONTEXT.sub("", text, count=1)


def history(session: Session, entry_id: str | None = None) -> list[dict]:
    """Messages along the current branch (or up to `entry_id`); tool results carry their UI payloads.

    Each message: {"role": "user", "content"} or {"role": "assistant", "content", "components"} or
    {"role": "tool_call", "id", "name", "arguments"} or
    {"role": "tool", "id", "name", "content", "ui"} or
    {"role": "compaction", "content": summary, "tokens_before"} where the model's view was summarized
    (the full transcript is still listed).
    """
    out: list[dict] = []
    names: dict[str, str] = {}
    components = session.reply_components()
    last_result: str | None = None  # the latest delegation result, for {{result}} in replies
    for entry in session.path_to(entry_id):
        item = entry["data"]
        if entry["type"] == "compaction":
            out.append({"role": "compaction", "content": item["summary"], "tokens_before": item.get("tokens_before", 0)})
            continue
        if entry["type"] != "item" or not isinstance(item, dict):
            continue
        role, kind = item.get("role"), item.get("type")
        if role == "user" and kind in (None, "message"):
            out.append({"role": role, "content": strip_context(message_text(item))})
        elif role == "assistant" and kind in (None, "message"):
            text = strip_hints(message_text(item))[0]  # the live stream hides <ui:…> tags too
            if last_result is not None:
                text = text.replace(RESULT_MARKER, last_result)
            out.append({"role": role, "content": text, "components": components.get(entry["id"], [])})
        elif kind == "function_call":
            names[item.get("call_id", "")] = item.get("name", "")
            out.append({"role": "tool_call", "id": item.get("call_id"), "name": item.get("name"), "arguments": item.get("arguments")})
        elif kind == "function_call_output":
            raw_ui = (item.get(CUSTOM_DATA_KEY) or {}).get("ui")
            full = delegation_result(raw_ui, str(item.get("output", "")))
            if full is not None and not str(item.get("output", "")).startswith("Error"):
                last_result = full
            ui = payload(raw_ui, text=str(item.get("output", ""))[:500])
            out.append({
                "role": "tool", "id": item.get("call_id"), "name": names.get(item.get("call_id", ""), ""),
                "content": item.get("output"), "ui": ui.model_dump() if ui else None,
            })
    return out
