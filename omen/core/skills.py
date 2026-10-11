"""Skills: instructions + tools that the agent loads on demand.

A skill is a folder:

    skills/web/
      SKILL.md      # frontmatter (name, description, keywords) + instructions
      tools.py      # optional: TOOLS = [tool, ...]
      helpers.py    # anything tools.py imports relatively (`from .helpers import x`)

Only `name: description` lines are always in the system prompt. A skill's
tools are registered up front but disabled (SDK `is_enabled`) until the skill
is loaded, either by the model calling `load_skill(name)` or by the keyword
pre-router before a run (small models under-trigger skills). Loading also puts
the skill's instructions into the system prompt. Up to MAX_LOADED skills stay
loaded across turns; loading another evicts the least recently used.
"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.machinery
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from agents import FunctionTool, RunContextWrapper

from omen.core.tools import ToolResult, tool

MAX_LOADED = 3
STATE_KEY = "skills"  # OmenContext.state[STATE_KEY] = [loaded skill names, most recent last]
_PACKAGE = "omen_skills"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path
    keywords: list[str] = field(default_factory=list)
    tools: list[FunctionTool] = field(default_factory=list)


def parse_skill_md(text: str) -> tuple[dict[str, Any], str]:
    """Split `---` YAML frontmatter from the markdown body."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text.strip()
    meta = yaml.safe_load(match.group(1)) or {}
    return meta, match.group(2).strip()


def _load_tools(folder: Path, name: str) -> list[FunctionTool]:
    """Import `folder/tools.py` as a package module so it can use relative imports."""
    if not (folder / "tools.py").exists():
        return []
    if _PACKAGE not in sys.modules:
        root = importlib.util.module_from_spec(importlib.machinery.ModuleSpec(_PACKAGE, None, is_package=True))
        root.__path__ = []
        sys.modules[_PACKAGE] = root
    package_name = f"{_PACKAGE}.{name}"
    for key in [k for k in sys.modules if k == package_name or k.startswith(package_name + ".")]:
        del sys.modules[key]  # fresh import on reload
    spec = importlib.machinery.ModuleSpec(package_name, None, is_package=True)
    spec.submodule_search_locations = [str(folder)]
    package = importlib.util.module_from_spec(spec)
    package.__path__ = [str(folder)]
    sys.modules[package_name] = package
    module = importlib.import_module(f"{package_name}.tools")
    return list(getattr(module, "TOOLS", []))


def discover(directories: list[Path]) -> dict[str, Skill]:
    """Find skills in `directories` (later directories override earlier ones by name)."""
    skills: dict[str, Skill] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for skill_md in sorted(directory.glob("*/SKILL.md")):
            meta, body = parse_skill_md(skill_md.read_text(encoding="utf-8"))
            name = str(meta.get("name") or skill_md.parent.name)
            skills[name] = Skill(
                name=name,
                description=str(meta.get("description", "")).strip(),
                body=body,
                path=skill_md.parent,
                keywords=[str(k).lower() for k in meta.get("keywords", [])],
                tools=_load_tools(skill_md.parent, name),
            )
    return skills


def loaded(state: dict) -> list[str]:
    return state.setdefault(STATE_KEY, [])


class Skills:
    def __init__(self, directories: list[Path]):
        self.directories = directories
        self.skills = discover(directories)

    def reload(self) -> None:
        self.skills = discover(self.directories)

    # -- loading ------------------------------------------------------------ #

    def load(self, name: str, state: dict) -> Skill | None:
        skill = self.skills.get(name)
        if skill is None:
            return None
        names = loaded(state)
        if name in names:
            names.remove(name)
        names.append(name)
        del names[:-MAX_LOADED]
        return skill

    def route(self, text: str) -> str | None:
        """Keyword pre-router: the best-matching skill for a user message, if any."""
        words = set(re.findall(r"[a-z0-9']+", text.lower()))
        best, best_score = None, 0
        for skill in self.skills.values():
            score = 0
            for keyword in skill.keywords:
                if " " in keyword:
                    score += 2 if keyword in text.lower() else 0
                elif keyword in words:
                    score += 1
            if score > best_score:
                best, best_score = skill.name, score
        return best

    # -- what the agent sees ------------------------------------------------- #

    def roster(self) -> str:
        return "\n".join(f"- {s.name}: {s.description}" for s in self.skills.values())

    def active_instructions(self, state: dict) -> str:
        parts = []
        for name in loaded(state):
            skill = self.skills.get(name)
            if skill and skill.body:
                tools = ", ".join(t.name for t in skill.tools)
                header = f"## Skill: {skill.name}" + (f" (tools: {tools})" if tools else "")
                parts.append(f"{header}\n{skill.body}")
        return "\n\n".join(parts)

    def gated_tools(self) -> list[FunctionTool]:
        """Every skill tool, enabled only while its skill is loaded."""
        gated = []
        for skill in self.skills.values():
            for t in skill.tools:
                gated.append(dataclasses.replace(t, is_enabled=_enabled_when_loaded(skill.name)))
        return gated

    def load_skill_tool(self) -> FunctionTool:
        skills = self

        @tool
        def load_skill(ctx: RunContextWrapper[Any], name: str) -> ToolResult:
            """Load a skill to get its instructions and tools. Use it before tasks a skill covers.

            Args:
                name: Skill name from the skills list.
            """
            state = _state(ctx)
            skill = skills.load(name.strip().lower(), state)
            if skill is None:
                return ToolResult(
                    f"Error: no skill named '{name}'. Skills: {', '.join(skills.skills)}.",
                    error="invalid_args",
                )
            tools = ", ".join(t.name for t in skill.tools) or "none (instructions only)"
            return ToolResult(
                f"Loaded skill '{skill.name}'. Tools now available: {tools}.",
                details={"type": "skill_loaded", "skill": skill.name},
            )

        return load_skill


def _state(ctx: Any) -> dict:
    app = getattr(ctx, "context", None)
    state = getattr(app, "state", None)
    return state if isinstance(state, dict) else {}


def _enabled_when_loaded(name: str):
    def is_enabled(ctx: Any, agent: Any) -> bool:
        return name in loaded(_state(ctx))

    return is_enabled
