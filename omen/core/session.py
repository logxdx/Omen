"""Session store: an append-only JSONL tree.

Each line is an entry `{id, parent_id, type, ts, data}`. The conversation is
the path from the root to the current leaf. Branching just moves the leaf to an
earlier entry; the next append starts a new branch there, and the old branch
stays in the file. That makes "go back to before the model went off the rails"
cheap, which matters with small models.

Entry types: "message" (an OpenAI-style chat message), "label" (a name for an
entry; does not move the leaf). Later phases add "compaction" and "custom".
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

# Entry types that annotate the tree without becoming the conversation leaf.
_SIDE_ENTRIES = {"label"}


class Session:
    def __init__(self, path: Path | None = None):
        """Open (or create) a session file. `path=None` keeps it in memory only."""
        self.path = path
        self.entries: dict[str, dict] = {}
        self.leaf: str | None = None
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self.entries[entry["id"]] = entry
                    if entry["type"] not in _SIDE_ENTRIES:
                        self.leaf = entry["id"]

    @classmethod
    def create(cls, directory: Path) -> Session:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return cls(directory / f"{stamp}-{uuid.uuid4().hex[:6]}.jsonl")

    def append(self, type: str, data: dict) -> str:
        parent = data.get("target") if type in _SIDE_ENTRIES else self.leaf
        entry = {
            "id": uuid.uuid4().hex[:12],
            "parent_id": parent,
            "type": type,
            "ts": time.time(),
            "data": data,
        }
        self.entries[entry["id"]] = entry
        if type not in _SIDE_ENTRIES:
            self.leaf = entry["id"]
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry["id"]

    def add_message(self, message: dict) -> str:
        return self.append("message", message)

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

    def messages(self) -> list[dict]:
        """The conversation along the current branch, as chat messages."""
        return [e["data"] for e in self.path_to() if e["type"] == "message"]

    def children(self, entry_id: str | None) -> list[dict]:
        return [
            e for e in self.entries.values()
            if e["parent_id"] == entry_id and e["type"] not in _SIDE_ENTRIES
        ]

    def labels(self) -> dict[str, str]:
        """{entry_id: label}; the latest label wins."""
        return {
            e["data"]["target"]: e["data"]["name"]
            for e in self.entries.values() if e["type"] == "label"
        }
