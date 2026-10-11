"""Omen events → AG-UI protocol events (ag-ui-protocol), for the web UI and any AG-UI client.

Mapping:
- text, reasoning, tool calls/results, run lifecycle → their AG-UI counterparts
- a tool result's UIPayload, an extracted UI component, an `ask_user` question
  → ACTIVITY_SNAPSHOT (activity_type = component type / "question")
- a delegated persona's events → SUBAGENT_STARTED / FINISHED around them, every
  nested event tagged with `subagent_run_id`
- everything else (usage, skill loads, injected messages) → CUSTOM
"""

from __future__ import annotations

from typing import Any

from ag_ui import core as ag

from omen.core import events as om


class AgUiMapper:
    """Stateful: AG-UI needs paired start/end events that Omen's stream implies."""

    def __init__(self, thread_id: str, run_id: str):
        self.thread_id = thread_id
        self.run_id = run_id
        self._step: str | None = None
        self._reasoning: str | None = None
        self._subagents: dict[str, str] = {}  # delegate tool_call_id → subagent_run_id

    def map(self, event: om.Event) -> list[ag.BaseEvent]:
        if isinstance(event, om.SubagentEvent):
            return self._subagent(event)
        return self._map(event, None)

    # -- top level --------------------------------------------------------------- #

    def _map(self, event: om.Event, sub: str | None) -> list[ag.BaseEvent]:
        tag = {"subagent_run_id": sub} if sub else {}
        out: list[ag.BaseEvent] = []

        if isinstance(event, om.RunStarted):
            return [ag.RunStartedEvent(thread_id=self.thread_id, run_id=self.run_id)]
        if isinstance(event, om.RunFinished):
            out += self._close_reasoning(None) + self._close_step(None)
            return out + [ag.RunFinishedEvent(thread_id=self.thread_id, run_id=self.run_id, result={"reason": event.reason})]
        if isinstance(event, om.RunError):
            return [ag.RunErrorEvent(message=event.message)]

        if isinstance(event, om.StepStarted):
            if sub:
                return []  # nested steps are implied by the subagent's events
            out += self._close_reasoning(None) + self._close_step(None)
            self._step = f"step {event.step}"
            return out + [ag.StepStartedEvent(step_name=self._step)]

        if isinstance(event, om.ReasoningContent):
            if sub:
                return []
            if self._reasoning is None:
                self._reasoning = f"reasoning-{event.message_id}"
                out += [
                    ag.ReasoningStartEvent(message_id=self._reasoning),
                    ag.ReasoningMessageStartEvent(message_id=self._reasoning, role="reasoning"),
                ]
            return out + [ag.ReasoningMessageContentEvent(message_id=self._reasoning, delta=event.delta)]

        if isinstance(event, om.TextMessageStart):
            out += [] if sub else self._close_reasoning(None)
            return out + [ag.TextMessageStartEvent(message_id=event.message_id, role="assistant", **tag)]
        if isinstance(event, om.TextMessageContent):
            if not event.delta:
                return []
            return [ag.TextMessageContentEvent(message_id=event.message_id, delta=event.delta, **tag)]
        if isinstance(event, om.TextMessageEnd):
            return [ag.TextMessageEndEvent(message_id=event.message_id, **tag)]

        if isinstance(event, om.ToolCallStart):
            out += [] if sub else self._close_reasoning(None)
            return out + [ag.ToolCallStartEvent(tool_call_id=event.tool_call_id, tool_call_name=event.name, **tag)]
        if isinstance(event, om.ToolCallArgs):
            return [ag.ToolCallArgsEvent(tool_call_id=event.tool_call_id, delta=event.delta or "{}", **tag)]
        if isinstance(event, om.ToolCallEnd):
            return [ag.ToolCallEndEvent(tool_call_id=event.tool_call_id, **tag)]
        if isinstance(event, om.ToolCallResult):
            sub_run = self._subagents.pop(event.tool_call_id, None) if not sub else None
            if sub_run:
                if event.error:
                    out.append(ag.SubagentErrorEvent(subagent_run_id=sub_run, message=event.content))
                else:
                    out.append(ag.SubagentFinishedEvent(subagent_run_id=sub_run, result=event.content))
            out.append(ag.ToolCallResultEvent(
                message_id=f"result-{event.tool_call_id}", tool_call_id=event.tool_call_id,
                content=event.content, role="tool", **tag,
            ))
            if isinstance(event.details, dict):
                out.append(self._activity(f"ui-{event.tool_call_id}", event.details, tag, tool_call_id=event.tool_call_id))
            return out

        if isinstance(event, om.UIComponent):
            index = event.payload.get("type", "ui")
            return [self._activity(f"ui-{event.message_id}-{index}", event.payload, tag, source_message_id=event.message_id)]
        if isinstance(event, om.UserQuestion):
            return [ag.ActivitySnapshotEvent(
                message_id=f"question-{event.question_id}", activity_type="question",
                content={"question_id": event.question_id, "question": event.question, "options": event.options},
                **tag,
            )]
        if isinstance(event, om.Custom):
            return [ag.CustomEvent(name=event.name, value=event.value, **tag)]
        return []

    # -- nesting ----------------------------------------------------------------- #

    def _subagent(self, event: om.SubagentEvent) -> list[ag.BaseEvent]:
        out: list[ag.BaseEvent] = []
        sub = self._subagents.get(event.tool_call_id)
        if sub is None:
            sub = f"sub-{event.tool_call_id}"
            self._subagents[event.tool_call_id] = sub
            out.append(ag.SubagentStartedEvent(
                subagent_run_id=sub, name=event.persona, parent_tool_call_id=event.tool_call_id,
            ))
        return out + self._map(event.event, sub)

    def _activity(self, message_id: str, ui: dict, tag: dict, **extra: Any) -> ag.ActivitySnapshotEvent:
        return ag.ActivitySnapshotEvent(
            message_id=message_id, activity_type=str(ui.get("type", "unknown")),
            content={**ui, **extra}, **tag,
        )

    def _close_reasoning(self, _: Any) -> list[ag.BaseEvent]:
        if self._reasoning is None:
            return []
        message_id, self._reasoning = self._reasoning, None
        return [ag.ReasoningMessageEndEvent(message_id=message_id), ag.ReasoningEndEvent(message_id=message_id)]

    def _close_step(self, _: Any) -> list[ag.BaseEvent]:
        if self._step is None:
            return []
        name, self._step = self._step, None
        return [ag.StepFinishedEvent(step_name=name)]
