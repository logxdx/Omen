"""Assembles the main assistant from a persona: prompt, core tools, skills, memory, delegation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from agents import Agent, FunctionTool, Model

from omen.config import DEFAULT_PERSONA, OMEN_HOME, PERSONAS_DIRS, SKILLS_DIRS, ModelConfig, main_model
from omen.core.ask import ask_user
from omen.core.delegate import delegate_tool
from omen.core.events import Custom, Event
from omen.core.memory import Memory
from omen.core.models import make_model, make_settings
from omen.core.personas import Persona, discover
from omen.core.skills import Skills, loaded

GUIDANCE = (
    "Answer in plain sentences. Use a tool only when you need information or an action you can't do "
    "yourself. If the user tells you something worth keeping (names, dates, preferences), call remember."
)
DELEGATION = (
    "Specialists: hand them a subtask with delegate (they are not skills; don't load_skill them). "
    "If the user names a specialist, delegate to it. When delegate returns, give the user the result "
    "itself (the full draft, the facts), not just a note that it's done."
)
FALLBACK_PERSONA = Persona(name="assistant", description="Default assistant.", body="You are a concise personal assistant.", path=Path())


@dataclass
class Assistant:
    agent: Agent
    persona: Persona
    personas: dict[str, Persona]
    skills: Skills
    memory: Memory
    use_router: bool = True
    core_tools: list[FunctionTool] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)  # build_assistant kwargs, for switch()

    def switch(self, name: str) -> Assistant:
        """A new assistant with another main persona (same skills dirs, memory, model)."""
        if name not in self.personas or not self.personas[name].main:
            raise KeyError(name)
        return build_assistant(**{**self.options, "persona": name})

    def reload(self) -> None:
        """Re-scan skill folders (after editing a SKILL.md or tools.py)."""
        self.skills.reload()
        self.agent.tools = self.core_tools + self.skills.gated_tools()

    def prepare(self, text: str, state: dict) -> list[Event]:
        """Runs before each user message: keep the persona's skills loaded, then route by keyword."""
        events: list[Event] = []
        for name in self.persona.skills:
            if name not in loaded(state) and self.skills.load(name, state):
                events.append(Custom("skill_loaded", {"skill": name, "by": "persona"}))
        if self.use_router:
            name = self.skills.route(text)
            if name is not None and name not in loaded(state):
                self.skills.load(name, state)
                events.append(Custom("skill_loaded", {"skill": name, "by": "router"}))
        return events


def build_assistant(
    *,
    persona: str | None = None,
    config: ModelConfig | None = None,
    model: Model | None = None,
    skills_dirs: list[Path] | None = None,
    personas_dirs: list[Path] | None = None,
    memory_path: Path | None = None,
    extra_tools: list[FunctionTool] | None = None,
    use_router: bool = True,
) -> Assistant:
    options = dict(
        config=config, model=model, skills_dirs=skills_dirs, personas_dirs=personas_dirs,
        memory_path=memory_path, extra_tools=extra_tools, use_router=use_router,
    )
    config = config or main_model()
    skills = Skills(skills_dirs if skills_dirs is not None else SKILLS_DIRS)
    personas = discover(personas_dirs if personas_dirs is not None else PERSONAS_DIRS)
    main = personas.get((persona or DEFAULT_PERSONA).lower()) or FALLBACK_PERSONA
    memory = Memory(memory_path or OMEN_HOME / "memory" / "facts.jsonl")
    settings = make_settings(config)

    def model_for(p: Persona) -> Model:
        if model is not None:
            return model
        return make_model(replace(config, model=p.model) if p.model else config)

    specialists = [p for p in personas.values() if p.delegate and p.name != main.name]
    delegate = None
    if specialists:
        agents = [_specialist_agent(p, skills, model_for(p), settings) for p in specialists]
        delegate = delegate_tool(agents, max_turns={p.name: p.max_turns for p in specialists})

    def instructions(ctx: Any, agent: Agent) -> str:
        state = getattr(ctx.context, "state", {}) if ctx.context is not None else {}
        now = datetime.now().astimezone()
        parts = [main.body, GUIDANCE]
        if delegate is not None:
            parts.append(DELEGATION + "\n" + "\n".join(f"- {p.name}: {p.description}" for p in specialists))
        parts.append(f"Current date and time: {now:%A, %d %B %Y, %H:%M %Z}.")
        recalled = memory.prompt_section(state.get("user_message", ""))
        if recalled:
            parts.append(recalled)
        if skills.skills:
            parts.append("Skills (call load_skill with the name before a task a skill covers):\n" + skills.roster())
        active = skills.active_instructions(state)
        if active:
            parts.append(active)
        return "\n\n".join(parts)

    redirects = {p.name: f"It is a specialist: use delegate with persona '{p.name}'." for p in specialists}
    core = [skills.load_skill_tool(redirects), memory.remember_tool(), ask_user]
    if delegate is not None:
        core.append(delegate)
    core += list(extra_tools or [])
    agent = Agent(
        name=main.name,
        instructions=instructions,
        model=model_for(main),
        model_settings=settings,
        tools=core + skills.gated_tools(),
    )
    return Assistant(
        agent=agent, persona=main, personas=personas, skills=skills, memory=memory,
        use_router=use_router, core_tools=core, options=options,
    )


def _specialist_agent(persona: Persona, skills: Skills, model: Model, settings: Any) -> Agent:
    """A persona as a delegation target: its skills' tools always on, their instructions in its prompt."""
    tools: list[FunctionTool] = []
    sections = [persona.body]
    for name in persona.skills:
        skill = skills.skills.get(name)
        if skill is None:
            continue
        tools.extend(skill.tools)
        if skill.body:
            sections.append(f"## Skill: {skill.name}\n{skill.body}")
    return Agent(
        name=persona.name,
        handoff_description=persona.description,
        instructions="\n\n".join(sections),
        model=model,
        model_settings=settings,
        tools=tools,
    )
