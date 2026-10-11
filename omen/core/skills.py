"""Skills: instructions + tools that the agent loads on demand.

A skill is a folder:

    skills/web/
      SKILL.md      # frontmatter (name, description, keywords) + instructions
      tools.py      # optional: TOOLS = [tool, ...]
      helpers.py    # anything tools.py imports relatively (`from .helpers import x`)

Cache-friendly layout (see plan.md, "Prompt cache"): the system prompt and the
tool list never change during a session, so the model server can reuse its
prompt cache. Concretely:
- only `name: description` lines are in the (frozen) system prompt;
- every skill tool is always visible; calling one marks its skill as loaded;
- a skill's instructions are appended to the conversation exactly once: as the
  result of `load_skill(name)`, or in the next user message's context block when
  the keyword pre-router (or a tool call) loaded it (`pending_instructions`).
"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.machinery
import importlib.util
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from agents import FunctionTool, RunContextWrapper

from omen.core.tools import ToolResult, tool

logger = logging.getLogger(__name__)
MAX_LOADED = 3
STATE_KEY = "skills"  # OmenContext.state[STATE_KEY] = [loaded skill names, most recent last]
SHOWN_KEY = "skills_shown"  # skills whose instructions are already in the conversation
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
    """Split `---` YAML frontmatter from the markdown body. Raises ValueError on bad YAML."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text.strip()
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"invalid frontmatter: {e}") from e
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a mapping")
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
            try:
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
            except Exception as e:  # one broken skill must not take the assistant down
                logger.warning("skipping skill %s: %s", skill_md.parent, e)
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

    def instructions(self, skill: Skill) -> str:
        tools = ", ".join(t.name for t in skill.tools)
        header = f"Skill '{skill.name}' instructions" + (f" (tools: {tools})" if tools else "")
        return f"{header}:\n{skill.body}"

    def pending_instructions(self, state: dict) -> list[str]:
        """Instructions of loaded skills not yet shown in this conversation (then marked shown)."""
        shown = state.setdefault(SHOWN_KEY, [])
        out = []
        for name in loaded(state):
            skill = self.skills.get(name)
            if skill and skill.body and name not in shown:
                shown.append(name)
                out.append(self.instructions(skill))
        return out

    def gated_tools(self) -> list[FunctionTool]:
        """Every skill tool, always visible (a constant tool list keeps the prompt cache warm).

        Calling one marks its skill as loaded, so its instructions follow in the next context block.
        """
        return [
            dataclasses.replace(t, on_invoke_tool=_marks_loaded(self, skill.name, t.on_invoke_tool))
            for skill in self.skills.values()
            for t in skill.tools
        ]

    def load_skill_tool(self, redirects: dict[str, str] | None = None) -> FunctionTool:
        """`redirects` maps names that aren't skills (e.g. personas) to a hint for the model."""
        skills = self
        redirects = redirects or {}

        @tool
        def load_skill(ctx: RunContextWrapper[Any], name: str) -> ToolResult:
            """Get a skill's instructions before a task it covers (its tools are always available).

            Args:
                name: Skill name from the skills list.
            """
            state = _state(ctx)
            key = name.strip().lower()
            skill = skills.load(key, state)
            if skill is None and key in redirects:
                return ToolResult(f"Error: '{name}' is not a skill. {redirects[key]}", error="invalid_args")
            if skill is None:
                return ToolResult(
                    f"Error: no skill named '{name}'. Skills: {', '.join(skills.skills)}.",
                    error="invalid_args",
                )
            shown = state.setdefault(SHOWN_KEY, [])
            if skill.name not in shown:
                shown.append(skill.name)
            body = skills.instructions(skill) if skill.body else f"Skill '{skill.name}' has no instructions."
            return ToolResult(
                f"Loaded skill '{skill.name}'.\n\n{body}",
                details={"type": "skill_loaded", "skill": skill.name},
            )

        return load_skill


def _state(ctx: Any) -> dict:
    app = getattr(ctx, "context", None)
    state = getattr(app, "state", None)
    return state if isinstance(state, dict) else {}


def _marks_loaded(skills: Skills, name: str, invoke: Any):
    async def on_invoke_tool(ctx: Any, arguments: str) -> Any:
        state = _state(ctx)
        if name not in loaded(state):
            skills.load(name, state)
        return await invoke(ctx, arguments)

    return on_invoke_tool
