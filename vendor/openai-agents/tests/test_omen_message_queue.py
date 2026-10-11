"""Omen fork: mid-run message queue (RunConfig.message_queue)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agents import Agent, MessageQueue, RunConfig, Runner, UserMessageItem, function_tool

from .fake_model import FakeModel
from .test_responses import get_function_tool_call, get_text_message
from .utils.simple_session import SimpleListSession


def _roles_and_types(items: list[Any]) -> list[str]:
    out = []
    for item in items:
        if isinstance(item, dict):
            out.append(item.get("role") or item.get("type"))
        else:
            out.append(getattr(item, "role", None) or getattr(item, "type", None))
    return out


def _user_texts(items: list[Any]) -> list[str]:
    return [i["content"] for i in items if isinstance(i, dict) and i.get("role") == "user"]


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [True, False])
async def test_message_queued_during_tool_is_injected_after_tool_output(streamed: bool):
    queue = MessageQueue()

    @function_tool
    def check_inbox() -> str:
        queue.put("also check the weather")  # the user types while the tool runs
        return "no new mail"

    model = FakeModel()
    model.add_multiple_turn_outputs(
        [
            [get_function_tool_call("check_inbox", json.dumps({}), call_id="c1")],
            [get_text_message("No mail; weather is sunny.")],
        ]
    )
    agent = Agent(name="a", model=model, tools=[check_inbox])
    session = SimpleListSession()
    config = RunConfig(message_queue=queue)

    if streamed:
        result = Runner.run_streamed(agent, "check my inbox", run_config=config, session=session)
        names = [e.name async for e in result.stream_events() if e.type == "run_item_stream_event"]
        assert "user_message_injected" in names
        assert names.index("user_message_injected") > names.index("tool_output")
    else:
        result = await Runner.run(agent, "check my inbox", run_config=config, session=session)

    second_input = model.last_turn_args["input"]
    assert _roles_and_types(second_input)[-2:] == ["function_call_output", "user"]
    assert second_input[-1]["content"] == "also check the weather"
    assert result.final_output == "No mail; weather is sunny."
    assert queue.pending() == 0

    injected = [i for i in result.new_items if isinstance(i, UserMessageItem)]
    assert [i.raw_item["content"] for i in injected] == ["also check the weather"]
    assert _user_texts(result.to_input_list()) == ["check my inbox", "also check the weather"]

    stored = await session.get_items()
    assert _user_texts(stored) == ["check my inbox", "also check the weather"]
    types = _roles_and_types(stored)
    assert types.index("function_call_output") < len(types) - 1 - types[::-1].index("user")


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [True, False])
async def test_pending_message_turns_final_output_into_another_turn(streamed: bool):
    queue = MessageQueue()
    queue.put("and in French?")
    model = FakeModel()
    model.add_multiple_turn_outputs(
        [[get_text_message("Good morning")], [get_text_message("Bonjour")]]
    )
    agent = Agent(name="a", model=model)
    config = RunConfig(message_queue=queue)

    if streamed:
        result = Runner.run_streamed(agent, "say good morning", run_config=config)
        async for _ in result.stream_events():
            pass
    else:
        result = await Runner.run(agent, "say good morning", run_config=config)

    assert result.final_output == "Bonjour"
    second_input = model.last_turn_args["input"]
    assert _user_texts(second_input) == ["say good morning", "and in French?"]
    assert _roles_and_types(second_input)[-2:] == ["assistant", "user"]


@pytest.mark.asyncio
async def test_without_queue_behaviour_is_unchanged():
    model = FakeModel()
    model.add_multiple_turn_outputs([[get_text_message("hi")]])
    agent = Agent(name="a", model=model)
    result = await Runner.run(agent, "hello", run_config=RunConfig())
    assert result.final_output == "hi"
    assert not any(isinstance(i, UserMessageItem) for i in result.new_items)


@pytest.mark.asyncio
async def test_nested_agent_tool_does_not_drain_parent_queue():
    queue = MessageQueue()

    @function_tool
    def slow_lookup() -> str:
        queue.put("thanks, also X")  # arrives while the nested agent is running
        return "looked up"

    inner_model = FakeModel()
    inner_model.add_multiple_turn_outputs(
        [
            [get_function_tool_call("slow_lookup", "{}", call_id="i1")],
            [get_text_message("inner done")],
        ]
    )
    inner = Agent(name="inner", model=inner_model, tools=[slow_lookup])

    outer_model = FakeModel()
    outer_model.add_multiple_turn_outputs(
        [
            [get_function_tool_call("ask_inner", json.dumps({"input": "go"}), call_id="o1")],
            [get_text_message("outer done")],
        ]
    )
    outer = Agent(
        name="outer",
        model=outer_model,
        tools=[inner.as_tool(tool_name="ask_inner", tool_description="inner agent")],
    )

    result = await Runner.run(outer, "start", run_config=RunConfig(message_queue=queue))

    assert result.final_output == "outer done"
    assert _user_texts(inner_model.last_turn_args["input"]) == ["go"]
    assert _user_texts(outer_model.last_turn_args["input"]) == ["start", "thanks, also X"]
