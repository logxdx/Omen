"""Assembles the main assistant: prompt, core tools, skills, memory and the skill pre-router."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from agents import Agent, FunctionTool, Model

from omen.config import OMEN_HOME, SKILLS_DIRS, ModelConfig, main_model
from omen.core.ask import ask_user
from omen.core.events import Custom, Event
from omen.core.memory import Memory
from omen.core.models import make_model, make_settings
from omen.core.skills import Skills, loaded

BASE_PROMPT = (
    "You are Jarvis, a concise personal assistant. Answer in plain sentences. "
    "Use a tool only when you need information or an action you can't do yourself. "
    "If the user tells you something worth keeping (names, dates, preferences), call remember."
)


@dataclass
class Assistant:
    agent: Agent
    skills: Skills
    memory: Memory
    use_router: bool = True
    core_tools: list[FunctionTool] = field(default_factory=list)

    def reload(self) -> None:
        """Re-scan skill folders (after editing a SKILL.md or tools.py)."""
        self.skills.reload()
        self.agent.tools = self.core_tools + self.skills.gated_tools()

    def prepare(self, text: str, state: dict) -> list[Event]:
        """Runs before each user message: load the skill the message most likely needs."""
        if not self.use_router:
            return []
        name = self.skills.route(text)
        if name is None or name in loaded(state):
            return []
        self.skills.load(name, state)
        return [Custom("skill_loaded", {"skill": name, "by": "router"})]


def build_assistant(
    *,
    config: ModelConfig | None = None,
    model: Model | None = None,
    skills_dirs: list[Path] | None = None,
    memory_path: Path | None = None,
    extra_tools: list[FunctionTool] | None = None,
    use_router: bool = True,
) -> Assistant:
    config = config or main_model()
    skills = Skills(skills_dirs if skills_dirs is not None else SKILLS_DIRS)
    memory = Memory(memory_path or OMEN_HOME / "memory" / "facts.jsonl")

    def instructions(ctx: Any, agent: Agent) -> str:
        state = getattr(ctx.context, "state", {}) if ctx.context is not None else {}
        now = datetime.now().astimezone()
        parts = [BASE_PROMPT, f"Current date and time: {now:%A, %d %B %Y, %H:%M %Z}."]
        recalled = memory.prompt_section(state.get("user_message", ""))
        if recalled:
            parts.append(recalled)
        if skills.skills:
            parts.append(
                "Skills (call load_skill with the name before a task a skill covers):\n" + skills.roster()
            )
        active = skills.active_instructions(state)
        if active:
            parts.append(active)
        return "\n\n".join(parts)

    core = [skills.load_skill_tool(), memory.remember_tool(), ask_user] + list(extra_tools or [])
    agent = Agent(
        name="Jarvis",
        instructions=instructions,
        model=model or make_model(config),
        model_settings=make_settings(config),
        tools=core + skills.gated_tools(),
    )
    return Assistant(agent=agent, skills=skills, memory=memory, use_router=use_router, core_tools=core)
