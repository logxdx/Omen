"""Components from assistant text: deterministic rules first, a small JSON model for the rest.

Rules (no LLM):
- a markdown table           → `table`
- a closing question + 2-6 listed options → `choice`

Hint tags: the main model may end a reply with `<ui:chart>` or `<ui:card>` (one
token is easy even for small models; authoring JSON is not). The extractor model
then fills that component's flat schema from the reply, using the server's JSON
schema mode (llama.cpp / Ollama / OpenAI `response_format`), validates it, retries
once with the validation error, and otherwise gives up (the text still stands).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from omen.config import ModelConfig
from omen.ui.components import EXTRACTABLE, Choice, Table, UIPayload, payload

logger = logging.getLogger(__name__)

HINT = re.compile(r"<ui:(table|chart|card)>", re.IGNORECASE)
_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_OPTION = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(.+?)\s*$")


def strip_hints(text: str) -> tuple[str, list[str]]:
    """Remove `<ui:kind>` tags; return (clean text, requested kinds in order, no duplicates)."""
    kinds = list(dict.fromkeys(k.lower() for k in HINT.findall(text)))
    return HINT.sub("", text).strip(), kinds


def table_from_markdown(text: str) -> Table | None:
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        header, separator = _ROW.match(lines[i]), _SEPARATOR.match(lines[i + 1])
        if not (header and separator):
            continue
        columns = [_cell(c) for c in header.group(1).split("|")]
        rows = []
        for line in lines[i + 2 :]:
            row = _ROW.match(line)
            if not row:
                break
            cells = [_cell(c) for c in row.group(1).split("|")]
            rows.append((cells + [""] * len(columns))[: len(columns)])
        if rows:
            before = [line.strip() for line in lines[max(0, i - 3) : i] if line.strip()]
            title = before[-1].rstrip(":").strip("#* ") if before else None
            return Table(type="table", title=title or None, columns=columns[:12], rows=rows[:50])
    return None


def _cell(text: str) -> str:
    """A table cell as plain text (markdown emphasis and code marks removed)."""
    return re.sub(r"(\*\*|__|`)", "", text).strip()


def choices_from_text(text: str) -> Choice | None:
    """A question followed by a short list of options at the end of the reply."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    options: list[str] = []
    while lines and (match := _OPTION.match(lines[-1])):
        options.insert(0, match.group(1).strip("*_ "))
        lines.pop()
    if not (2 <= len(options) <= 6) or not lines or not lines[-1].rstrip().endswith(("?", "?:", ":")):
        return None
    if any(len(o) > 80 for o in options):
        return None
    return Choice(type="choice", question=lines[-1].strip().rstrip(":"), options=options)


Complete = Callable[[list[dict], dict], Awaitable[str]]


class Extractor:
    """Fills one EXTRACTABLE component from text with a JSON-schema-constrained completion."""

    def __init__(self, config: ModelConfig | None = None, complete: Complete | None = None):
        self.config = config
        self._complete = complete or self._litellm_complete

    async def extract(self, kind: str, context: str) -> UIPayload | None:
        model = EXTRACTABLE.get(kind)
        if model is None:
            return None
        schema = _props_schema(model.model_json_schema())
        messages = [
            {"role": "system", "content": (
                f"Extract a {kind} for a UI component from the CONTEXT. Use only information in the CONTEXT. "
                "Reply with JSON matching the schema, nothing else."
            )},
            {"role": "user", "content": f"CONTEXT:\n{context[:6000]}"},
        ]
        for attempt in range(2):
            try:
                raw = await self._complete(messages, {"name": kind, "schema": schema})
            except Exception as e:  # model unavailable, timeout, ...: no component, the text stands
                logger.warning("extractor call failed for %s: %s", kind, e)
                return None
            try:
                data = json.loads(_json_text(raw))
                if isinstance(data, dict) and data.get("url") and str(data["url"]) not in context:
                    data["url"] = None  # small models invent plausible links; keep only ones in the text
                component = model.model_validate({**data, "type": kind})
                return payload(component.model_dump(), text=context[:300])
            except (json.JSONDecodeError, ValidationError, TypeError) as e:
                logger.info("extractor attempt %d for %s failed: %s", attempt + 1, kind, e)
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That was not valid: {str(e)[:300]}. Reply with corrected JSON only."},
                ]
        return None

    async def _litellm_complete(self, messages: list[dict], json_schema: dict) -> str:
        import litellm

        config = self.config
        if config is None:
            from omen.config import extractor_model

            config = extractor_model()
        response = await litellm.acompletion(
            model=config.model,
            api_base=config.base_url,
            api_key=config.api_key,
            messages=messages,
            temperature=0,
            max_tokens=800,
            response_format={"type": "json_schema", "json_schema": json_schema},
        )
        return response.choices[0].message.content or ""


def _props_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The component schema without its `type` discriminator (the extractor fills props only)."""
    schema = json.loads(json.dumps(schema))
    schema.get("properties", {}).pop("type", None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r != "type"]
    schema.pop("title", None)
    return schema


def _json_text(raw: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


async def components_for(
    text: str, extractor: Extractor | None, supported: set[str] | None = None
) -> list[UIPayload]:
    """All components for one assistant reply. `supported=None` means every type."""

    def wanted(kind: str) -> bool:
        return supported is None or kind in supported

    clean, hints = strip_hints(text)
    found: list[UIPayload] = []
    if wanted("table") and (table := table_from_markdown(clean)):
        found.append(payload(table.model_dump(), text=f"Table: {', '.join(table.columns)}"))
    if wanted("choice") and (choice := choices_from_text(clean)):
        found.append(payload(choice.model_dump(), text=choice.question))
    have = {p.type for p in found}
    for kind in hints:
        if kind in have or not wanted(kind) or extractor is None:
            continue
        extracted = await extractor.extract(kind, clean)
        if extracted is not None:
            found.append(extracted)
    return [p for p in found if p is not None]
