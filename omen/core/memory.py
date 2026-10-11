"""Long-term memory: facts the user wants kept across sessions.

`remember(fact)` is a core tool (always visible). Recall is automatic: facts
relevant to the current message are put into the system prompt each turn,
because small models forget to look things up.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from agents import RunContextWrapper

from omen.core.tools import ToolResult, tool

STOPWORDS = set(
    "a an and are as at be but by do does for from had has have he her his how i if in is it its "
    "me my of on or our she so than that the their them they this to us was we were what when "
    "where which who why will with you your about can could would should please tell know".split()
)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS and len(w) > 1}


class Memory:
    def __init__(self, path: Path):
        self.path = path

    def facts(self) -> list[dict]:
        """Live facts, oldest first (deletions are tombstone lines in the same file)."""
        if not self.path.exists():
            return []
        entries = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        deleted = {e["id"] for e in entries if e.get("deleted")}
        return [e for e in entries if not e.get("deleted") and e["id"] not in deleted]

    def add(self, fact: str) -> dict:
        entry = {"id": uuid.uuid4().hex[:8], "fact": fact.strip(), "ts": time.time()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def forget(self, fact_id: str) -> bool:
        if not any(f["id"] == fact_id for f in self.facts()):
            return False
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": fact_id, "deleted": True, "ts": time.time()}) + "\n")
        return True

    def recall(self, text: str, limit: int = 5) -> list[dict]:
        """Facts sharing words with `text`, best first. With few facts, all of them."""
        facts = self.facts()
        if len(facts) <= limit:
            return facts
        query = _words(text)
        scored = [(len(query & _words(f["fact"])), f["ts"], f) for f in facts]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return [f for _, _, f in scored[:limit]]

    def prompt_section(self, text: str) -> str:
        facts = self.recall(text)
        if not facts:
            return ""
        lines = "\n".join(f"- {f['fact']}" for f in facts)
        return f"Things you know about the user:\n{lines}"

    def remember_tool(self):
        memory = self

        @tool
        def remember(ctx: RunContextWrapper[Any], fact: str) -> ToolResult:
            """Save a fact about the user to long-term memory, e.g. names, dates, preferences.

            Args:
                fact: One short, self-contained sentence, e.g. "The user's sister is called Anna."
            """
            if not fact.strip():
                return ToolResult("Error: invalid arguments for remember: fact is empty.", error="invalid_args")
            entry = memory.add(fact)
            return ToolResult(f"Saved: {entry['fact']}", details={"type": "memory_saved", "fact": entry["fact"]})

        return remember
