"""Personas: markdown files that define an agent (voice, specialist or both).

    personas/researcher.md
    ---
    name: researcher
    description: Finds and checks facts on the web and reports them with sources.
    skills: [web]        # preloaded: the persona always has these skills' tools
    max_turns: 8         # cap for a delegated run
    main: true           # can be the main agent (/persona researcher)
    delegate: true       # the main agent can hand it subtasks via `delegate`
    model: openai/other  # optional, defaults to the main model
    ---
    Instructions (the persona's system prompt).

Voices (jarvis, vanessa, ...) are `main: true, delegate: false`. Specialists are
usually both. Personas never get the `delegate` tool themselves (one level only).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from omen.core.skills import parse_skill_md

logger = logging.getLogger(__name__)


@dataclass
class Persona:
    name: str
    description: str
    body: str
    path: Path
    skills: list[str] = field(default_factory=list)
    max_turns: int = 8
    main: bool = True
    delegate: bool = True
    model: str | None = None


def discover(directories: list[Path]) -> dict[str, Persona]:
    """Find personas in `directories` (later directories override earlier ones by name)."""
    personas: dict[str, Persona] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            try:
                meta, body = parse_skill_md(path.read_text(encoding="utf-8"))
                name = str(meta.get("name") or path.stem).lower()
                personas[name] = Persona(
                    name=name,
                    description=str(meta.get("description", "")).strip(),
                    body=body,
                    path=path,
                    skills=[str(s) for s in meta.get("skills") or []],
                    max_turns=int(meta.get("max_turns", 8)),
                    main=bool(meta.get("main", True)),
                    delegate=bool(meta.get("delegate", True)),
                    model=meta.get("model"),
                )
            except (ValueError, TypeError) as e:  # one broken persona must not take the assistant down
                logger.warning("skipping persona %s: %s", path, e)
    return personas
