"""Omen fork: tools can read the model-visible conversation (ToolContext.conversation_history)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agents import Agent, RunContextWrapper, Runner, function_tool
from agents.tool_context import ToolContext

from .fake_model import FakeModel
from .test_responses import get_function_tool_call, get_text_message


def _summary(items: list[Any]) -> list[str]:
    out = []
    for item in items:
        assert isinstance(item, dict)
        if item.get("role") == "user":
            out.append(f"user:{item['content']}")
        elif item.get("type") == "function_call":
            out.append(f"call:{item['name']}")
        elif item.get("type") == "function_call_output":
            out.append(f"output:{item['output']}")
        elif item.get("role") == "assistant" or item.get("type") == "message":
            out.append("assistant")
        else:
            out.append(str(item.get("type")))
    return out


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [True, False])
async def test_tool_sees_history_without_in_flight_calls(streamed: bool):
    seen: dict[str, list[str]] = {}

    @function_tool
    def lookup(ctx: ToolContext[Any], what: str) -> str:
        seen[what] = _summary(ctx.conversation_history)
        return f"found {what}"

    model = FakeModel()
    model.add_multiple_turn_outputs(
        [
            [get_function_tool_call("lookup", json.dumps({"what": "a"}), call_id="c1")],
            [
                get_text_message("Now two more."),
                get_function_tool_call("lookup", json.dumps({"what": "b"}), call_id="c2"),
                get_function_tool_call("lookup", json.dumps({"what": "c"}), call_id="c3"),
            ],
            [get_text_message("done")],
        ]
    )
    agent = Agent(name="a", model=model, tools=[lookup])

    if streamed:
        result = Runner.run_streamed(agent, "find things")
        async for _ in result.stream_events():
            pass
    else:
        result = await Runner.run(agent, "find things")

    assert result.final_output == "done"
    # First call: only the user message; the in-flight call itself is excluded.
    assert seen["a"] == ["user:find things"]
    # Parallel calls b and c see the completed a-round plus the assistant text of their own
    # response, but neither sibling call (no outputs yet).
    expected = ["user:find things", "call:lookup", "output:found a", "assistant"]
    assert seen["b"] == expected
    assert seen["c"] == expected


@pytest.mark.asyncio
async def test_history_includes_session_and_prior_input():
    seen: list[list[str]] = []

    @function_tool
    def note(ctx: RunContextWrapper[Any]) -> str:
        seen.append(_summary(ctx.conversation_history))
        return "ok"

    model = FakeModel()
    model.add_multiple_turn_outputs(
        [[get_function_tool_call("note", "{}", call_id="n1")], [get_text_message("fine")]]
    )
    agent = Agent(name="a", model=model, tools=[note])
    prior = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": "now this"},
    ]
    await Runner.run(agent, prior)
    assert seen == [["user:earlier question", "assistant", "user:now this"]]


@pytest.mark.asyncio
async def test_agent_tool_subrun_has_its_own_history():
    inner_seen: list[list[str]] = []

    @function_tool
    def inner_tool(ctx: ToolContext[Any]) -> str:
        inner_seen.append(_summary(ctx.conversation_history))
        return "inner ok"

    inner_model = FakeModel()
    inner_model.add_multiple_turn_outputs(
        [[get_function_tool_call("inner_tool", "{}", call_id="i1")], [get_text_message("i done")]]
    )
    inner = Agent(name="inner", model=inner_model, tools=[inner_tool])

    outer_model = FakeModel()
    outer_model.add_multiple_turn_outputs(
        [
            [get_function_tool_call("ask_inner", json.dumps({"input": "sub task"}), call_id="o1")],
            [get_text_message("o done")],
        ]
    )
    outer = Agent(
        name="outer",
        model=outer_model,
        tools=[inner.as_tool(tool_name="ask_inner", tool_description="inner")],
    )
    await Runner.run(outer, "top task")
    assert inner_seen == [["user:sub task"]]
