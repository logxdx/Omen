"""Compaction: when the conversation nears the context budget, summarize the old part.

Small models plan worse, and decode slower, as the context fills (ling3: ~115 tok/s at
2k tokens, 65 at 64k). Before a new user message, if the context is over
`trigger_tokens`, the conversation is cut at a user-message boundary (a tool call and
its result are never separated) and the most recent `keep_recent_tokens` stay verbatim.
Before the cut, each user request and final answer is kept word for word and the tool calls
between them shrink to one line ("[3 tool calls: read_file ×2, web_search]"); only if that
is still over `condensed_tokens` are the oldest turns summarized into fixed sections by one
side-model call (Phase 9, after Agent Zero's topic compression).

The summary is stored as a `compaction` entry in the session tree (the full history stays
in the file and in the UIs); the model sees it prepended to the first kept user message.
The prefix changes once per compaction, then the prompt cache warms up again.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable

from omen.config import ModelConfig

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Summarize the TRANSCRIPT of a conversation between a user and an assistant so \
the assistant can continue it without the transcript. Fill in this template with concrete facts from \
the transcript, as short bullet points under every heading (write "- none" if nothing fits):

## Goal
- what the user wants overall
## Constraints and preferences
- dates, budgets, people, likes/dislikes, rules the user gave (exact values)
## Progress
- what was done or answered so far
## Decisions
- choices made
## Next steps
- what is still open
## Files touched
- paths written or read

Keep exact names, numbers, dates, paths, URLs and IDs. Keep decisions apart from assumptions, and mark \
anything not confirmed in the transcript as (unverified). If the transcript starts with an earlier summary, \
merge its facts in. Output only the filled template."""

Complete = Callable[[list[dict]], Awaitable[str]]
_CONTEXT = re.compile(r"^\s*<context>.*?</context>\s*", re.DOTALL)
SUMMARY_HEADER = "<summary>\nThe earlier conversation, condensed:\n"
_SUMMARY = re.compile(r"^<summary>\nThe earlier conversation, (?:condensed|summarized):\n(.*?)\n</summary>\s*", re.DOTALL)
VERBATIM_HEADING = "## Earlier turns, word for word (tool calls shortened)"


def estimate_tokens(items: list[Any]) -> int:
    """Rough token count of session items (~4 characters per token of JSON)."""
    return len(json.dumps(items, ensure_ascii=False, default=str)) // 4


def is_user_message(item: Any) -> bool:
    return isinstance(item, dict) and item.get("role") == "user" and item.get("type") in (None, "message")


def split_point(items: list[Any], keep_recent_tokens: int) -> int:
    """Index of the first item to keep verbatim: the earliest user message whose suffix fits
    the budget, but always the last user message at least. 0 = nothing to compact."""
    starts = [i for i, item in enumerate(items) if is_user_message(item)]
    if len(starts) < 2:
        return 0
    cut = starts[-1]
    for i in reversed(starts[:-1]):
        if estimate_tokens(items[i:]) > keep_recent_tokens:
            break
        cut = i
    return cut if cut > 0 else 0


def render(items: list[Any], tool_chars: int = 600) -> str:
    """Items as a plain transcript for the summarizer (context blocks dropped, tool output cut)."""
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind, role = item.get("type"), item.get("role")
        if role in ("user", "assistant") and kind in (None, "message"):
            text = _text(item)
            if role == "user":
                if earlier := _SUMMARY.match(text):  # a previous compaction: merge it in
                    lines.append(f"Earlier summary:\n{earlier.group(1).strip()}")
                    text = text[earlier.end():]
                text = _CONTEXT.sub("", text, count=1)
            if text.strip():
                lines.append(f"{role.capitalize()}: {text.strip()}")
        elif kind == "function_call":
            lines.append(f"Assistant called {item.get('name')}({item.get('arguments', '')})")
        elif kind == "function_call_output":
            output = str(item.get("output", ""))
            if len(output) > tool_chars:
                output = output[:tool_chars] + f" … [{len(output) - tool_chars} more characters]"
            lines.append(f"Tool result: {output}")
    return "\n\n".join(lines)


def condense(items: list[Any]) -> str:
    """Turns as text: each user request and final answer verbatim, the tool calls between them as one line."""
    lines: list[str] = []
    calls: list[str] = []
    answer = ""

    def end_turn() -> None:
        if calls:
            counts = Counter(calls)
            names = ", ".join(f"{n} ×{c}" if c > 1 else n for n, c in counts.items())
            lines.append(f"[{len(calls)} tool call{'s' if len(calls) > 1 else ''}: {names}]")
        if answer:
            lines.append(f"Assistant: {answer}")

    for item in items:
        if not isinstance(item, dict):
            continue
        if is_user_message(item):
            end_turn()
            calls, answer = [], ""
            text = _text(item)
            if earlier := _SUMMARY.match(text):
                lines.append(f"Earlier summary:\n{earlier.group(1).strip()}")
                text = text[earlier.end():]
            text = _CONTEXT.sub("", text, count=1).strip()
            if text:
                lines.append(f"User: {text}")
        elif item.get("type") == "function_call":
            calls.append(str(item.get("name", "tool")))
        elif item.get("role") == "assistant" and item.get("type") in (None, "message"):
            answer = _text(item).strip() or answer  # the last one in a turn is the final answer
    end_turn()
    return "\n\n".join(lines)


def with_summary(items: list[Any], summary: str) -> list[Any]:
    """Prepend the summary to the first user message (keeps user/assistant alternation)."""
    out = list(items)
    for i, item in enumerate(out):
        if is_user_message(item):
            block = f"{SUMMARY_HEADER}{summary.strip()}\n</summary>\n\n"
            content = item.get("content")
            if isinstance(content, list):
                content = [{"type": "input_text", "text": block}, *content]
            else:
                content = block + (content or "")
            out[i] = {**item, "content": content}
            return out
    return [{"role": "user", "content": f"{SUMMARY_HEADER}{summary.strip()}\n</summary>"}, *out]


def substantive(summary: str) -> bool:
    """A summary with facts in it, not just the template's headings (small models sometimes echo it)."""
    facts = [
        line.strip("-*• ").strip() for line in summary.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return sum(len(f) for f in facts if f.lower() not in ("none", "n/a", "")) >= 40


def _text(item: dict) -> str:
    content = item.get("content")
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


@dataclass
class Compactor:
    trigger_tokens: int = 24000
    keep_recent_tokens: int = 6000
    condensed_tokens: int | None = None  # budget for verbatim old turns; None = keep_recent_tokens
    complete: Complete | None = None
    config: ModelConfig | None = None
    # State that tracks what earlier context blocks showed (omen.assistant / omen.core.skills):
    # cleared so memories and skill instructions summarized away are shown again.
    reset_state_keys: tuple[str, ...] = ("memory_shown", "skills_shown")

    async def maybe_compact(self, session: Any, state: dict, force: bool = False) -> dict | None:
        """Compact `session` if it is over budget (or `force`). Returns what happened, or None."""
        entries = session.item_entries()
        items = session.items()  # the model's view: a previous summary is part of what gets summarized
        if len(items) != len(entries):
            return None
        size = state.get("context_tokens") or estimate_tokens(items)
        if not force and size < self.trigger_tokens:
            return None
        cut = split_point(items, self.keep_recent_tokens)
        if cut == 0:
            return None
        old = items[:cut]
        # Newest old turns that fit the budget stay word for word (tool calls shortened); only the
        # turns before them go to the side model.
        budget = self.keep_recent_tokens if self.condensed_tokens is None else self.condensed_tokens
        keep_from = len(old)
        for i in reversed([i for i, item in enumerate(old) if is_user_message(item)]):
            if len(condense(old[i:])) // 4 > budget:
                break
            keep_from = i
        verbatim = condense(old[keep_from:]) if keep_from < len(old) else ""
        if keep_from == 0:
            summary, method = verbatim, "condensed"
        else:
            try:
                summarized = (await (self.complete or self._litellm_complete)([
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": f"TRANSCRIPT:\n{render(old[:keep_from])}"},
                ])).strip()
            except Exception as e:  # no summary, no compaction: the run goes on with the full context
                logger.warning("compaction summary failed: %s", e)
                return None
            summarized = re.sub(r"<think>.*?</think>", "", summarized, flags=re.DOTALL).strip()
            if not substantive(summarized):
                logger.warning("compaction summary was empty or only headings; keeping the full context")
                return None
            summary = f"{summarized}\n\n{VERBATIM_HEADING}\n{verbatim}" if verbatim else summarized
            method = "summarized"
        session.compact(summary, first_kept=entries[cut][0], tokens_before=size)
        state["context_tokens"] = None  # unknown until the next request reports usage
        for key in self.reset_state_keys:
            state.pop(key, None)
        return {
            "tokens_before": size, "summarized_items": cut, "kept_items": len(items) - cut,
            "method": method, "summary": summary,
        }

    async def _litellm_complete(self, messages: list[dict]) -> str:
        import litellm

        config = self.config
        if config is None:
            from omen.config import extractor_model

            config = replace(extractor_model(), max_tokens=1500)  # side slot, thinking off locally
        response = await litellm.acompletion(
            model=config.model, api_base=config.base_url, api_key=config.api_key, messages=messages,
            temperature=0, max_tokens=config.max_tokens, extra_body=config.extra_body or None,
        )
        return response.choices[0].message.content or ""
