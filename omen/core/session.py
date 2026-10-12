"""Session store: an append-only JSONL tree that implements the Agents SDK `Session` protocol.

Each line is an entry `{id, parent_id, type, ts, data}`. The conversation the
model sees is the path from the root to the current leaf. Branching moves the
leaf to an earlier entry; the next append starts a new branch there and the old
branch stays in the file. That makes "go back to before the model went off the
rails" cheap, which matters with small models.

Entry types:
- "item": an SDK input item (message, function_call, function_call_output, ...).
  Tool outputs may carry UI details under `_agents_custom_data` (fork patch).
- "label": names an entry; never becomes the leaf.
- "ui": a component extracted from an assistant reply (`{target, component}`), for
  re-rendering; never becomes the leaf, so the model never sees it.
- "compaction": `{summary, first_kept, tokens_before}` on the main line. The model's view
  of the branch becomes: the summary, then the items from `first_kept` on (see
  omen/core/compaction.py). The entries before it stay in the file and the UIs.

Delegation sub-runs are recorded with `fork()` as *detached* branches: they hang
off the main conversation but never become its leaf, so the main agent never
sees them unless you branch into them explicitly.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.memory import SessionSettings

from omen.core.compaction import with_summary

CUSTOM_DATA_KEY = "_agents_custom_data"
_SIDE_TYPES = {"label", "ui"}


class Session:
    session_settings: SessionSettings | None = None

    def __init__(self, path: Path | None = None, session_id: str | None = None):
        """Open (or create) a session file. `path=None` keeps it in memory only."""
        self.path = path
        self.session_id = session_id or (path.stem if path else uuid.uuid4().hex[:12])
        self.entries: dict[str, dict] = {}
        self.leaf: str | None = None
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self.entries[entry["id"]] = entry
                    if self._is_main(entry):
                        self.leaf = entry["id"]

    @classmethod
    def create(cls, directory: Path) -> Session:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return cls(directory / f"{stamp}-{uuid.uuid4().hex[:6]}.jsonl")

    # -- SDK Session protocol ------------------------------------------------ #

    async def get_items(self, limit: int | None = None) -> list[Any]:
        items = self.items()
        return items[-limit:] if limit else items

    async def add_items(self, items: list[Any]) -> None:
        for item in items:
            self.append("item", _plain(item))

    async def pop_item(self) -> Any | None:
        if self.leaf is None:
            return None
        entry = self.entries[self.leaf]
        self.leaf = entry["parent_id"]
        return entry["data"] if entry["type"] == "item" else None

    async def clear_session(self) -> None:
        self.leaf = None

    # -- tree operations ----------------------------------------------------- #

    def append(
        self,
        type: str,
        data: dict,
        *,
        parent_id: str | None | object = ...,
        detached: bool = False,
        meta: dict | None = None,
    ) -> str:
        """Add an entry. By default it extends the current leaf and becomes the new leaf."""
        if parent_id is ...:
            parent_id = data.get("target") if type in _SIDE_TYPES else self.leaf
        entry: dict[str, Any] = {
            "id": uuid.uuid4().hex[:12],
            "parent_id": parent_id,
            "type": type,
            "ts": time.time(),
            "data": data,
        }
        if detached:
            entry["detached"] = True
        if meta:
            entry["meta"] = meta
        self.entries[entry["id"]] = entry
        if self._is_main(entry):
            self.leaf = entry["id"]
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return entry["id"]

    def fork(self, items: list[Any], meta: dict | None = None, from_id: str | None | object = ...) -> str | None:
        """Record `items` as a detached branch off `from_id` (default: current leaf). Returns its last id."""
        parent = self.leaf if from_id is ... else from_id
        last = None
        for item in items:
            last = self.append(
                "item",
                _plain(item),
                parent_id=parent if last is None else last,
                detached=True,
                meta=meta if last is None else None,
            )
        return last

    def thread(self, entry_id: str) -> list[Any]:
        """Items of the detached branch ending at `entry_id` (a delegation's run, oldest first)."""
        items = []
        entry = self.entries.get(entry_id)
        while entry is not None and entry.get("detached"):
            if entry["type"] == "item":
                items.append(entry["data"])
            entry = self.entries.get(entry["parent_id"])
        return items[::-1]

    def label(self, entry_id: str, name: str) -> str:
        if entry_id not in self.entries:
            raise KeyError(entry_id)
        return self.append("label", {"target": entry_id, "name": name})

    def branch(self, entry_id: str | None) -> None:
        """Make `entry_id` the current leaf (None = start over from the root)."""
        if entry_id is not None and entry_id not in self.entries:
            raise KeyError(entry_id)
        self.leaf = entry_id

    def path_to(self, entry_id: str | None = None) -> list[dict]:
        """Entries from the root to `entry_id` (default: current leaf)."""
        chain = []
        current = entry_id if entry_id is not None else self.leaf
        while current is not None:
            entry = self.entries[current]
            chain.append(entry)
            current = entry["parent_id"]
        return chain[::-1]

    def items(self, entry_id: str | None = None) -> list[Any]:
        """SDK input items the model sees along the current branch (or up to `entry_id`):
        after a compaction, its summary plus the items it kept."""
        entries = self.item_entries(entry_id)
        items = [data for _, data in entries]
        compaction = self.last_compaction(entry_id)
        return with_summary(items, compaction["data"]["summary"]) if compaction else items

    def item_entries(self, entry_id: str | None = None) -> list[tuple[str, Any]]:
        """(entry id, item) pairs the model sees, without the summary (the latest compaction's
        kept items and everything after it)."""
        path = self.path_to(entry_id)
        start = 0
        for i in range(len(path) - 1, -1, -1):
            if path[i]["type"] == "compaction":
                kept = path[i]["data"]["first_kept"]
                start = next((j for j, e in enumerate(path) if e["id"] == kept), i)
                break
        return [(e["id"], e["data"]) for e in path[start:] if e["type"] == "item"]

    def last_compaction(self, entry_id: str | None = None) -> dict | None:
        for entry in reversed(self.path_to(entry_id)):
            if entry["type"] == "compaction":
                return entry
        return None

    def compact(self, summary: str, first_kept: str, tokens_before: int = 0) -> str:
        """Record a compaction on the current branch (see omen/core/compaction.py)."""
        if first_kept not in self.entries:
            raise KeyError(first_kept)
        return self.append("compaction", {"summary": summary, "first_kept": first_kept, "tokens_before": tokens_before})

    def children(self, entry_id: str | None) -> list[dict]:
        return [
            e for e in self.entries.values()
            if e["parent_id"] == entry_id and e["type"] not in _SIDE_TYPES
        ]

    def labels(self) -> dict[str, str]:
        """{entry_id: label}; the latest label wins."""
        return {
            e["data"]["target"]: e["data"]["name"]
            for e in self.entries.values() if e["type"] == "label"
        }

    def add_reply_component(self, reply_text: str, component: dict) -> str | None:
        """Attach a UI component to the latest assistant message with this text on the current branch."""
        for entry in reversed(self.path_to()):
            data = entry["data"]
            if entry["type"] == "item" and isinstance(data, dict) and data.get("role") == "assistant":
                if message_text(data) == reply_text:
                    return self.append("ui", {"target": entry["id"], "component": component})
        return None

    def reply_components(self) -> dict[str, list[dict]]:
        """{assistant message entry id: [components]}."""
        out: dict[str, list[dict]] = {}
        for e in self.entries.values():
            if e["type"] == "ui":
                out.setdefault(e["data"]["target"], []).append(e["data"]["component"])
        return out

    def ui_details(self) -> dict[str, Any]:
        """{tool call_id: UI details} along the current branch, for re-rendering components."""
        out = {}
        for item in self.items():
            if isinstance(item, dict) and item.get("type") == "function_call_output":
                ui = (item.get(CUSTOM_DATA_KEY) or {}).get("ui")
                if ui is not None:
                    out[item.get("call_id")] = ui
        return out

    # -- internals ----------------------------------------------------------- #

    @staticmethod
    def _is_main(entry: dict) -> bool:
        return entry["type"] not in _SIDE_TYPES and not entry.get("detached")


def message_text(item: dict) -> str:
    """The text of a message item (string content or a list of text parts)."""
    content = item.get("content")
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def _plain(item: Any) -> Any:
    """SDK items may be pydantic models; store them as plain JSON-able dicts."""
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_unset=True)
    return item
