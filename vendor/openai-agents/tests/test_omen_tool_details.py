"""Omen fork: tool output split into model content + UI details, persisted with the session."""

from __future__ import annotations

from typing import Any

import pytest

from agents import Agent, Runner, ToolCallOutputItem, function_tool
from agents.tool import FunctionToolCustomDataContext

from .fake_model import FakeModel
from .test_responses import get_function_tool_call, get_text_message
from .utils.simple_session import SimpleListSession


class Result:
    """What Omen tools return: short text for the model, structured data for the UI."""

    def __init__(self, content: str, details: dict[str, Any]):
        self.content = content
        self.details = details

    def __str__(self) -> str:
        return self.content


def _details(data: FunctionToolCustomDataContext) -> dict[str, Any] | None:
    return {"ui": data.output.details} if isinstance(data.output, Result) else None


@function_tool(custom_data_extractor=_details)
def get_weather(city: str) -> Result:
    """Weather for a city."""
    return Result(f"{city}: 18C, light rain", {"type": "weather", "city": city, "temp_c": 18})


def _outputs(items: list[Any]) -> list[dict[str, Any]]:
    return [i for i in items if isinstance(i, dict) and i.get("type") == "function_call_output"]


@pytest.mark.asyncio
async def test_model_sees_content_ui_gets_details_and_session_keeps_them():
    model = FakeModel()
    model.add_multiple_turn_outputs(
        [
            [get_function_tool_call("get_weather", '{"city": "Paris"}', call_id="w1")],
            [get_text_message("It's 18C in Paris.")],
        ]
    )
    agent = Agent(name="a", model=model, tools=[get_weather])
    session = SimpleListSession()

    result = Runner.run_streamed(agent, "weather in paris?", session=session)
    streamed_outputs = [
        e.item
        async for e in result.stream_events()
        if e.type == "run_item_stream_event" and e.name == "tool_output"
    ]

    # The UI receives the raw object (and custom_data) on the stream event.
    assert isinstance(streamed_outputs[0], ToolCallOutputItem)
    assert streamed_outputs[0].output.details["type"] == "weather"
    assert streamed_outputs[0].custom_data == {"ui": {"type": "weather", "city": "Paris", "temp_c": 18}}

    # The model only sees the text, and no SDK-only metadata.
    sent = _outputs(model.last_turn_args["input"])
    assert sent[0]["output"] == "Paris: 18C, light rain"
    assert "_agents_custom_data" not in sent[0]

    # The session keeps the details so a UI can re-render the component on reload.
    stored = _outputs(await session.get_items())
    assert stored[0]["_agents_custom_data"]["ui"]["temp_c"] == 18

    # Reloading the session for a new turn strips the metadata before the model sees it.
    model.add_multiple_turn_outputs([[get_text_message("You asked about Paris.")]])
    await Runner.run(agent, "what did I ask?", session=session)
    resent = _outputs(model.last_turn_args["input"])
    assert resent and all("_agents_custom_data" not in o for o in resent)


@pytest.mark.asyncio
async def test_outputs_without_custom_data_are_stored_unchanged():
    @function_tool
    def plain() -> str:
        return "plain text"

    model = FakeModel()
    model.add_multiple_turn_outputs(
        [[get_function_tool_call("plain", "{}", call_id="p1")], [get_text_message("ok")]]
    )
    session = SimpleListSession()
    await Runner.run(Agent(name="a", model=model, tools=[plain]), "go", session=session)
    stored = _outputs(await session.get_items())
    assert "_agents_custom_data" not in stored[0]
