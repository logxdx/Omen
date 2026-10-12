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
`follow_up: true` resumes the persona's latest branch on this conversation path
(its earlier subtasks, tool calls and results) and extends that same branch, so
the persona's next request is its previous one plus the new subtask.

Questions go up the chain: a persona that can't finish without information it
doesn't have calls `ask_superior(question)`, which ends its run; `delegate`
returns the question instead of a result. The main agent answers with another
`delegate` to the same persona (it continues where it stopped, no flag needed)
or first asks its own superior, the user, with `ask_user`.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from agents import Agent, FunctionTool, MaxTurnsExceeded, Runner
from agents.tool_context import ToolContext

from omen.core.events import SubagentEvent
from omen.core.session import CUSTOM_DATA_KEY
from omen.core.tools import ToolResult, extract_custom_data, tool, truncate
from omen.config import TOOL_CONTENT_MAX_CHARS

REPLY = (
    "Reply with the result for the main assistant: concise, complete, no preamble. If the task doesn't say "
    "something you need and your tools can't find it (who someone is, what it refers to), call ask_superior "
    "instead of asking in your reply."
)
SUBTASK_WITH_CONTEXT = (
    "The main assistant hands you this subtask:\n\n{task}\n\n"
    "Work only on this subtask, using the conversation above as context. " + REPLY
)
SUBTASK_ALONE = "The main assistant hands you this subtask:\n\n{task}\n\n" + REPLY
SUBTASK_FOLLOW_UP = "The main assistant hands you a follow-up to your earlier work above:\n\n{task}\n\n" + REPLY
SUBTASK_ANSWER = "The main assistant answers your question:\n\n{task}\n\nContinue your subtask. " + REPLY
QUESTION_RESULT = (
    "{persona} paused to ask: {question}\n"
    "It can't see this conversation; you can. If the conversation answers it, call "
    'delegate(persona="{persona}", task=<the answer, with the facts it needs>) now: it continues where it '
    "stopped. Only if nobody has said, ask the user with ask_user."
)
FROM_CONVERSATION = (
    "The conversation above, between the user and me, has what you need. Take the answer from it."
)
ASK_SUPERIOR = "ask_superior"


@tool
def ask_superior(question: str) -> ToolResult:
    """Ask the main assistant a question and pause your subtask until it answers.

    Only for what the task doesn't say and your tools can't find (who someone is, which one, what
    it's about). Use your tools first. The answer comes back as your next message.

    Args:
        question: One short, specific question (not the task itself).
    """
    return ToolResult("Your question went to the main assistant; its answer comes next.")


def with_questions(agent: Agent) -> Agent:
    """`agent` plus ask_superior, which ends its run (the question goes back to the caller)."""
    if any(getattr(t, "name", None) == ASK_SUPERIOR for t in agent.tools):
        return agent
    if agent.tool_use_behavior != "run_llm_again":  # the persona decides when it stops; leave it alone
        return agent
    return agent.clone(tools=[*agent.tools, ask_superior], tool_use_behavior={"stop_at_tool_names": [ASK_SUPERIOR]})


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
    questions: bool = True,
    auto_answer: bool = True,
) -> FunctionTool:
    """A tool that hands subtasks to `personas` (agents with their own instructions and tools).

    `max_turns` caps each delegated run; pass a dict to set it per persona name. With `questions`,
    each persona also gets ask_superior. With `auto_answer`, a persona that asks without having seen
    the conversation is resumed once with it before the question goes to the main model.
    """
    by_name = {p.name: with_questions(p) if questions else p for p in personas}

    def turns_for(persona_name: str) -> int:
        return max_turns.get(persona_name, 8) if isinstance(max_turns, dict) else max_turns
    roster = "\n".join(f"- {p.name}: {p.handoff_description or 'general help'}" for p in personas)
    description = (
        "Hand a subtask to a specialist and get its result back. By default the specialist sees "
        "only the task, so write it self-contained; set share_context to true if it needs the "
        "conversation so far, and follow_up to true to continue its earlier work (e.g. revise "
        "its draft). If it asks you a question instead, answer with delegate to the same specialist."
        f"\nSpecialists:\n{roster}"
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
            "follow_up": {
                "type": "boolean",
                "default": False,
                "description": "true: continue this specialist's earlier work in this conversation "
                "(it remembers its earlier tasks and results).",
            },
        },
        "required": ["persona", "task"],
    }

    async def invoke(ctx: ToolContext[Any], arguments: str) -> ToolResult:
        try:
            args = json.loads(arguments or "{}")
            persona_name, task = str(args["persona"]), str(args["task"]).strip()
            share_context = _as_bool(args.get("share_context", False))
            follow_up = args.get("follow_up", False)  # "auto" (named delegation): only right after it
            follow_up = "auto" if follow_up == "auto" else _as_bool(follow_up)
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

        app = ctx.context  # OmenContext when run through omen.core.runtime
        session = getattr(app, "session", None)
        thread_end, users_since = latest_thread(session.items(), persona.name) if session else (None, 0)
        thread = session.thread(thread_end) if thread_end else []
        answering = waiting_for_answer(thread) and users_since <= 1  # it asked us: this is the answer
        if not (answering or follow_up is True or (follow_up == "auto" and users_since <= 1)):
            thread_end, thread = None, []
        thread = [_without_details(i) for i in fork_history(thread, max_history_items)]
        history = fork_history(ctx.conversation_history, max_history_items) if share_context else []
        if answering:
            template = SUBTASK_ANSWER
        else:
            template = SUBTASK_FOLLOW_UP if thread else SUBTASK_WITH_CONTEXT if share_context else SUBTASK_ALONE
        subtask = {"role": "user", "content": template.format(task=task)}
        history += thread
        emit = getattr(app, "emit", None)
        run_config = (
            dataclasses.replace(ctx.run_config, message_queue=None, model_settings=None) if ctx.run_config else None
        )

        from omen.core.runtime import EventMapper  # runtime imports tools; avoid a cycle

        mapper = EventMapper()
        messages = history + [subtask]
        recorded = [subtask]  # what goes on the persona's branch (shared conversation excluded)
        conversation = fork_history(ctx.conversation_history or [], max_history_items)
        while True:
            result = Runner.run_streamed(
                persona, messages, context=app, max_turns=turns_for(persona.name), run_config=run_config
            )
            finished = True
            try:
                async for sdk_event in result.stream_events():
                    if emit:
                        for event in mapper.map(sdk_event):
                            emit(SubagentEvent(ctx.tool_call_id, persona.name, event))
            except MaxTurnsExceeded:
                finished = False
            run_items = [item.to_input_item() for item in result.new_items]
            recorded += run_items
            question = asked_question(result.new_items) if finished else None
            if not question or share_context or not (auto_answer and conversation):
                break
            # The superior's first answer: what it knows, i.e. the conversation (shared once, only
            # when the persona asks). If that doesn't answer it, the question goes up to the main model.
            share_context = True
            answer = {"role": "user", "content": SUBTASK_ANSWER.format(task=FROM_CONVERSATION)}
            messages = conversation + messages + run_items + [answer]
            recorded.append(answer)

        branch = None
        if session is not None:
            items = recorded
            meta = {"delegate": ctx.tool_call_id, "persona": persona.name}
            if thread_end:  # extend the persona's thread instead of starting a new branch
                branch = session.fork(items, meta={**meta, "follows": thread_end}, from_id=thread_end)
            else:
                branch = session.fork(items, meta=meta)
        details = {
            "type": "delegation",
            "persona": persona.name,
            "task": task,
            "shared_context": share_context,
            "follow_up": bool(thread),
            "branch": branch,
            "steps": mapper.step,
        }
        if not finished:
            return ToolResult(
                f"Error: {persona.name} did not finish within {turns_for(persona.name)} steps.",
                details=details,
                error="exception",
            )
        if question:  # no result yet: the caller answers with another delegate
            details["question"] = question
            return ToolResult(QUESTION_RESULT.format(persona=persona.name, question=question), details=details)
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
    """The full text of a finished delegation, from its UI details (else the capped content).

    None for a delegation that ended with a question: that goes to the main agent, not the user.
    """
    if isinstance(details, dict) and details.get("type") == "delegation" and not details.get("question"):
        return str(details.get("result") or content)
    return None


def asked_question(run_items: list[Any]) -> str | None:
    """The question if a persona's run stopped at ask_superior (after its last message)."""
    for item in reversed(run_items):
        if getattr(item, "type", None) == "message_output_item":
            return None
        raw = getattr(item, "raw_item", None)
        if getattr(item, "type", None) == "tool_call_item" and getattr(raw, "name", None) == ASK_SUPERIOR:
            try:
                question = json.loads(getattr(raw, "arguments", "") or "{}").get("question")
            except (json.JSONDecodeError, AttributeError):
                question = None
            return str(question or "").strip() or "(no question text)"
    return None


def waiting_for_answer(thread: list[Any]) -> bool:
    """True if a persona's thread ends with its ask_superior call (stored items are plain dicts)."""
    last = thread[-1] if thread else None
    if not isinstance(last, dict) or last.get("type") != "function_call_output":
        return False
    return any(
        isinstance(i, dict) and i.get("type") == "function_call"
        and i.get("call_id") == last.get("call_id") and i.get("name") == ASK_SUPERIOR
        for i in thread
    )


def latest_thread(items: list[Any], persona: str) -> tuple[str | None, int]:
    """(last entry of `persona`'s latest delegation branch on this path, user messages since it)."""
    users = 0
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        if item.get("role") == "user":
            users += 1
        elif item.get("type") == "function_call_output":
            ui = (item.get(CUSTOM_DATA_KEY) or {}).get("ui")
            if isinstance(ui, dict) and ui.get("type") == "delegation" and ui.get("persona") == persona:
                if ui.get("branch"):
                    return ui["branch"], users
    return None, users


def _without_details(item: Any) -> Any:
    """A branch item as the model may see it (UI details stay in the session)."""
    if isinstance(item, dict) and CUSTOM_DATA_KEY in item:
        return {k: v for k, v in item.items() if k != CUSTOM_DATA_KEY}
    return item


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
