"""Shared agent initialization helpers.

This module centralizes the multi-agent bootstrap logic so it can be reused
across multiple surfaces (CLI, ChatKit, etc.) without duplicating the
handoff wiring.
"""

from __future__ import annotations

from typing import Dict, Tuple

from agents import Agent

from my_agents import (
    analysis_agent,
    context_agent,
    resume_agent,
    filesystem_agent,
    ideation_agent,
    study_agent,
    triage_agent,
    web_search_agent,
)

# Module-level cache to ensure `add_handoffs` only runs once per process.
_CONFIGURED = False
_AGENT_REGISTRY: Dict[str, Agent] = {}
_PRIMARY_AGENT: Agent | None = None


def _configure_agents() -> None:
    """Wire handoffs and build the shared agent registry."""
    global _CONFIGURED, _AGENT_REGISTRY, _PRIMARY_AGENT
    if _CONFIGURED:
        return

    triage_agent.add_subagents([web_search_agent])
    triage_agent.add_handoffs([filesystem_agent])

    analysis_agent.add_handoffs([filesystem_agent])
    ideation_agent.add_subagents([web_search_agent])

    _AGENT_REGISTRY = {
        "orc": triage_agent.agent,
        "web": web_search_agent.agent,
        "fs": filesystem_agent.agent,
        "idea": ideation_agent.agent,
        "tutor": study_agent.agent,
        "analyst": analysis_agent.agent,
        "resume": resume_agent.agent,
        "memory": context_agent.agent,
    }
    _PRIMARY_AGENT = triage_agent.agent
    _CONFIGURED = True


def get_agent_registry() -> Tuple[Dict[str, Agent], Agent]:
    """Return the configured agent registry and primary triage agent."""
    _configure_agents()
    assert _PRIMARY_AGENT is not None
    return dict(_AGENT_REGISTRY), _PRIMARY_AGENT
