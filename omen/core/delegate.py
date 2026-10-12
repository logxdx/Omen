"""Delegation to personas, with optional forked context.

The main agent calls `delegate(persona, task, share_context=false)`. The main
model decides what the persona sees:
- `share_context: false` (default): only the task, so the persona works in a
  short, clean context;
- `share_context: true`: a *fork* of the main conversation (everything the main
  agent has seen so far, via the fork's `ToolContext.conversation_history`)
  plus the task.

The persona runs its own short loop with its own tools and returns only its
result. The main agent's context grows by one tool call + one result, not by
the persona's whole run.

The persona's run is recorded in the session as a detached branch (off the main
conversation, never part of it) and streamed to the UI as SUBAGENT_EVENTs.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from agents import Agent, FunctionTool, MaxTurnsExceeded, Runner
from agents.tool_context import ToolContext

from omen.core.events import SubagentEvent
from omen.core.tools import ToolResult, extract_custom_data, truncate
from omen.config import TOOL_CONTENT_MAX_CHARS

SUBTASK_WITH_CONTEXT = (
    "The main assistant hands you this subtask:\n\n{task}\n\n"
    "Work only on this subtask, using the conversation above as context. "
    "Reply with the result for the main assistant: concise, complete, no preamble."
)
SUBTASK_ALONE = (
    "The main assistant hands you this subtask:\n\n{task}\n\n"
    "Reply with the result for the main assistant: concise, complete, no preamble."
)


def _as_bool(value: Any) -> bool:
    """Small models sometimes send "true"/"false" strings."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)


def delegate_tool(
    personas: list[Agent],
    *,
    max_turns: int | dict[str, int] = 8,
    max_history_items: int | None = None,
    name: str = "delegate",
) -> FunctionTool:
    """A tool that hands subtasks to `personas` (agents with their own instructions and tools).

    `max_turns` caps each delegated run; pass a dict to set it per persona name.
    """
    by_name = {p.name: p for p in personas}

    def turns_for(persona_name: str) -> int:
        return max_turns.get(persona_name, 8) if isinstance(max_turns, dict) else max_turns
    roster = "\n".join(f"- {p.name}: {p.handoff_description or 'general help'}" for p in personas)
    description = (
        "Hand a subtask to a specialist and get its result back. By default the specialist sees "
        "only the task, so write it self-contained; set share_context to true if it needs the "
        f"conversation so far.\nSpecialists:\n{roster}"
    )
    schema = {
        "type": "object",
        "properties": {
            "persona": {"type": "string", "enum": list(by_name), "description": "Who should do it."},
            "task": {"type": "string", "description": "The subtask, with everything needed to do it."},
            "share_context": {
                "type": "boolean",
                "default": False,
                "description": "true: the specialist also sees the conversation so far.",
            },
        },
        "required": ["persona", "task"],
    }

    async def invoke(ctx: ToolContext[Any], arguments: str) -> ToolResult:
        try:
            args = json.loads(arguments or "{}")
            persona_name, task = str(args["persona"]), str(args["task"]).strip()
            share_context = _as_bool(args.get("share_context", False))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            return ToolResult(
                f"Error: invalid arguments for {name}: {e}. Send persona and task.",
                error="invalid_args",
            )
        persona = by_name.get(persona_name)
        if persona is None:
            return ToolResult(
                f"Error: invalid arguments for {name}: unknown persona '{persona_name}'. "
                f"Choose one of: {', '.join(by_name)}.",
                error="invalid_args",
            )
        if not task:
            return ToolResult(f"Error: invalid arguments for {name}: task is empty.", error="invalid_args")

        if share_context:
            subtask = {"role": "user", "content": SUBTASK_WITH_CONTEXT.format(task=task)}
            history = fork_history(ctx.conversation_history, max_history_items)
        else:
            subtask = {"role": "user", "content": SUBTASK_ALONE.format(task=task)}
            history = []
        app = ctx.context  # OmenContext when run through omen.core.runtime
        emit = getattr(app, "emit", None)
        run_config = (
            dataclasses.replace(ctx.run_config, message_queue=None, model_settings=None) if ctx.run_config else None
        )

        from omen.core.runtime import EventMapper  # runtime imports tools; avoid a cycle

        mapper = EventMapper()
        result = Runner.run_streamed(
            persona,
            history + [subtask],
            context=app,
            max_turns=turns_for(persona.name),
            run_config=run_config,
        )
        finished = True
        try:
            async for sdk_event in result.stream_events():
                if emit:
                    for event in mapper.map(sdk_event):
                        emit(SubagentEvent(ctx.tool_call_id, persona.name, event))
        except MaxTurnsExceeded:
            finished = False

        branch = None
        session = getattr(app, "session", None)
        if session is not None:
            branch = session.fork(
                [subtask] + [item.to_input_item() for item in result.new_items],
                meta={"delegate": ctx.tool_call_id, "persona": persona.name},
            )
        details = {
            "type": "delegation",
            "persona": persona.name,
            "task": task,
            "shared_context": share_context,
            "branch": branch,
            "steps": mapper.step,
        }
        if not finished:
            return ToolResult(
                f"Error: {persona.name} did not finish within {turns_for(persona.name)} steps.",
                details=details,
                error="exception",
            )
        output = str(result.final_output or "").strip() or "(no result)"
        details["result"] = output  # in full, for the screen ({{result}}, direct replies); the model gets it capped
        return ToolResult(truncate(output, TOOL_CONTENT_MAX_CHARS), details=details)

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=schema,
        on_invoke_tool=invoke,
        strict_json_schema=False,
        custom_data_extractor=extract_custom_data,
    )


RESULT_MARKER = "{{result}}"


def delegation_result(details: Any, content: str) -> str | None:
    """The full text of a successful delegation, from its UI details (else the capped content)."""
    if isinstance(details, dict) and details.get("type") == "delegation":
        return str(details.get("result") or content)
    return None


def fork_history(items: list[Any], max_items: int | None = None) -> list[Any]:
    """Copy of the main history for a sub-run, optionally keeping only the most recent items.

    Trimming starts at a user message so no tool output is separated from its call.
    """
    history = [dict(i) if isinstance(i, dict) else i for i in items]
    if max_items is None or len(history) <= max_items:
        return history
    history = history[-max_items:]
    for i, item in enumerate(history):
        if isinstance(item, dict) and item.get("role") == "user":
            return history[i:]
    return []
