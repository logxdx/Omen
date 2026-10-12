"""Assembles the main assistant from a persona: prompt, core tools, skills, memory, delegation.

Prompt-cache layout: the system prompt and tool list are identical on every request of a
session (no clock, no recalled memory, no per-turn skill text), so llama.cpp / Ollama /
API prompt caches stay warm. Everything that changes goes into a `<context>` block at
the start of each user message (`Assistant.context`), stored once and never rewritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from agents import Agent, FunctionTool, Model

from omen.config import (
    DEFAULT_PERSONA,
    MAX_TURNS,
    OMEN_HOME,
    PERSONAS_DIRS,
    SKILLS_DIRS,
    ModelConfig,
    main_model,
    side_config,
)
from omen.core.ask import ask_user
from omen.core.delegate import delegate_tool
from omen.core.events import Custom, Event
from omen.core.guard import guard_all
from omen.core.memory import Memory
from omen.core.models import make_model, make_settings
from omen.core.personas import Persona, discover
from omen.core.skills import Skills, loaded
from omen.ui.extract import CHART_REQUEST

GUIDANCE = (
    "Answer in plain sentences. Use a tool only when you need information or an action you can't do "
    "yourself. Call remember only for lasting personal facts (names, birthdays, preferences), not for data "
    "the user gives you for the current question. If the user says continue, go ahead or proceed, call the "
    "next tool now instead of saying you will."
)
DELEGATION = (
    "Specialists: hand them a subtask with delegate (they are not skills; don't load_skill them). "
    "Delegate only when a subtask needs a specialist's tools or a substantial piece of writing; answer simple "
    "questions yourself. If the user names a specialist, delegate to it. When delegate returns a draft or report the "
    "user should see in full, write {{result}} where it goes (the screen shows it in full) instead of copying it out; "
    "otherwise give the user the facts, not just a note that it's done."
)
UI_HINTS = (
    "The user's screen can show components. Write tables in markdown. ",
    {
        "chart": (
            "If numbers would read better as a chart, or the user asks for a chart, list the numbers in your reply "
            "and end it with <ui:chart> on its own line; the screen draws it. Never create files for charts."
        ),
        "card": "For a short summary of one thing (a place, product, person), end your reply with <ui:card> on its own line.",
    },
)
CONTEXT_NOTE = (
    "A user message may start with a <context> block (current time, things you know about the user, "
    "skill instructions). Use it silently; don't repeat it back."
)
CHART_NOTE = (
    "This message asks for a chart. The screen draws it from your reply: answer with the numbers as a "
    "short list (label: value) and end with <ui:chart>. Don't call tools, write files or draw it in text."
)
MEMORY_SHOWN_KEY = "memory_shown"
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
    specialists: list[str] = field(default_factory=list)  # delegation targets
    options: dict[str, Any] = field(default_factory=dict)  # build_assistant kwargs, for switch()

    def switch(self, name: str) -> Assistant:
        """A new assistant with another main persona (same skills dirs, memory, model)."""
        if name not in self.personas or not self.personas[name].main:
            raise KeyError(name)
        return build_assistant(**{**self.options, "persona": name})

    def reload(self) -> None:
        """Re-scan skill folders (after editing a SKILL.md or tools.py)."""
        self.skills.reload()
        self.agent.tools = guard_all(self.core_tools + self.skills.gated_tools(), max_turns=MAX_TURNS)

    def context(self, text: str, state: dict) -> str:
        """The `<context>` block for a new user message: time, new memories, new skill instructions."""
        now = datetime.now().astimezone()
        sections = [f"Now: {now:%A, %d %B %Y, %H:%M %Z}"]
        shown = state.setdefault(MEMORY_SHOWN_KEY, [])
        facts = [f for f in self.memory.recall(text) if f["id"] not in shown]
        if facts:
            shown.extend(f["id"] for f in facts)
            sections.append("Known about the user:\n" + "\n".join(f"- {f['fact']}" for f in facts))
        sections.extend(self.skills.pending_instructions(state))
        if "chart" in (state.get("ui_hints") or []) and CHART_REQUEST.search(text):
            sections.append(CHART_NOTE)  # small models otherwise draw ASCII charts into files
        return "<context>\n" + "\n\n".join(sections) + "\n</context>"

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
        named = self.named_specialist(text)
        if named:
            # The user asked for a specialist by name: delegate deterministically (small models
            # often do the work themselves instead, and llama.cpp ignores a named tool_choice).
            persona, task = named
            state["pre_call"] = {"name": "delegate", "arguments": {"persona": persona, "task": task}}
            events.append(Custom("delegate_hint", {"persona": persona}))
        return events

    def named_specialist(self, text: str) -> tuple[str, str] | None:
        """(persona, task) if the user addresses a specialist ("ask the writer to …", "@researcher …")."""
        for name in self.specialists:
            pattern = (
                rf"(@{re.escape(name)}\b|\b(ask|have|get|let|tell|use)\s+(the\s+|my\s+|your\s+)?{re.escape(name)}\b)"
                r"[\s,:]*(to\s+)?"
            )
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                task = (text[: match.start()] + text[match.end() :]).strip(" ,.:") or text
                return name, task[0].upper() + task[1:]
        return None


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
        side = make_settings(side_config(config))  # own llama.cpp slot if OMEN_SLOT_SIDE is set
        agents = [_specialist_agent(p, skills, model_for(p), side) for p in specialists]
        delegate = delegate_tool(agents, max_turns={p.name: p.max_turns for p in specialists})

    def instructions(ctx: Any, agent: Agent) -> str:
        # Constant for the session: anything that varies belongs in Assistant.context.
        state = getattr(ctx.context, "state", {}) if ctx.context is not None else {}
        parts = [main.body, GUIDANCE, CONTEXT_NOTE]
        if delegate is not None:
            parts.append(DELEGATION + "\n" + "\n".join(f"- {p.name}: {p.description}" for p in specialists))
        if skills.skills:
            parts.append(
                "Skills (their tools are always available; call load_skill with the name to get a skill's "
                "instructions before a task it covers):\n" + skills.roster()
            )
        hints = state.get("ui_hints") or []
        if hints:
            parts.append(UI_HINTS[0] + " ".join(UI_HINTS[1][k] for k in hints if k in UI_HINTS[1]))
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
        tools=guard_all(core + skills.gated_tools(), max_turns=MAX_TURNS),
    )
    return Assistant(
        agent=agent, persona=main, personas=personas, skills=skills, memory=memory,
        use_router=use_router, core_tools=core, options=options,
        specialists=[p.name for p in specialists],
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
        tools=guard_all(tools, max_turns=persona.max_turns),
    )
