"""Agent core on the forked OpenAI Agents SDK (vendor/openai-agents)."""

import agents as _agents

if not hasattr(_agents, "MessageQueue"):
    raise ImportError(
        "Omen needs its fork of the OpenAI Agents SDK (vendor/openai-agents). "
        "Run `uv sync` so pyproject's path source replaces the PyPI package."
    )

from omen.core.delegate import delegate_tool  # noqa: E402
from omen.core.runtime import OmenContext, Runtime  # noqa: E402
from omen.core.session import Session  # noqa: E402
from omen.core.tools import ToolResult, tool  # noqa: E402

__all__ = ["OmenContext", "Runtime", "Session", "ToolResult", "delegate_tool", "tool"]
