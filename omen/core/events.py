"""Events emitted by the agent loop.

Type names mirror AG-UI event types so the server (Phase 4) can forward them
with minimal translation. Every frontend (TUI, web, voice) consumes these.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar


@dataclass
class Event:
    type: ClassVar[str] = "EVENT"

    def to_dict(self) -> dict:
        return {"type": self.type, **asdict(self)}


@dataclass
class RunStarted(Event):
    type: ClassVar[str] = "RUN_STARTED"
    run_id: str


@dataclass
class RunFinished(Event):
    type: ClassVar[str] = "RUN_FINISHED"
    run_id: str
    reason: str  # "done" | "aborted" | "max_turns" | "loop" | "error"


@dataclass
class RunError(Event):
    type: ClassVar[str] = "RUN_ERROR"
    run_id: str
    message: str


@dataclass
class StepStarted(Event):
    type: ClassVar[str] = "STEP_STARTED"
    step: int


@dataclass
class TextMessageStart(Event):
    type: ClassVar[str] = "TEXT_MESSAGE_START"
    message_id: str


@dataclass
class TextMessageContent(Event):
    type: ClassVar[str] = "TEXT_MESSAGE_CONTENT"
    message_id: str
    delta: str


@dataclass
class TextMessageEnd(Event):
    type: ClassVar[str] = "TEXT_MESSAGE_END"
    message_id: str


@dataclass
class ReasoningContent(Event):
    type: ClassVar[str] = "REASONING_MESSAGE_CONTENT"
    message_id: str
    delta: str


@dataclass
class ToolCallStart(Event):
    type: ClassVar[str] = "TOOL_CALL_START"
    tool_call_id: str
    name: str


@dataclass
class ToolCallArgs(Event):
    type: ClassVar[str] = "TOOL_CALL_ARGS"
    tool_call_id: str
    delta: str


@dataclass
class ToolCallEnd(Event):
    type: ClassVar[str] = "TOOL_CALL_END"
    tool_call_id: str


@dataclass
class ToolCallResult(Event):
    type: ClassVar[str] = "TOOL_CALL_RESULT"
    tool_call_id: str
    name: str
    content: str  # what the model sees
    details: Any = None  # what the UI renders (UIPayload from Phase 4)
    error: str | None = None  # "unknown_tool" | "invalid_args" | "exception"


@dataclass
class Custom(Event):
    type: ClassVar[str] = "CUSTOM"
    name: str  # "usage" | "message_injected" | "agent"
    value: Any = None


@dataclass
class SubagentEvent(Event):
    """An event from a delegated persona's run, nested under the delegating tool call."""

    type: ClassVar[str] = "SUBAGENT_EVENT"
    tool_call_id: str
    persona: str
    event: Event

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "tool_call_id": self.tool_call_id,
            "persona": self.persona,
            "event": self.event.to_dict(),
        }
