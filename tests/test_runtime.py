import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

from agents import Agent, AgentHooks

from omen.core import Runtime, Session, ToolResult, tool
from omen.core.events import (
    Custom,
    RunError,
    RunFinished,
    RunStarted,
    StepStarted,
    TextMessageContent,
    TextMessageEnd,
    TextMessageStart,
    ToolCallArgs,
    ToolCallResult,
    ToolCallStart,
)
from omen.core.session import CUSTOM_DATA_KEY
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message


@tool
def get_weather(city: str) -> ToolResult:
    """Current weather for a city.

    Args:
        city: City name.
    """
    return ToolResult(f"{city}: 18°C", details={"type": "weather", "city": city, "temp_c": 18})


@tool
def broken() -> str:
    """Always fails."""
    raise RuntimeError("disk on fire")


@tool
async def slow_task() -> str:
    """Takes forever."""
    await asyncio.sleep(60)
    return "done"


def turns(*outputs):
    model = FakeModel()
    model.add_multiple_turn_outputs([o if isinstance(o, list) else [o] for o in outputs])
    return model


def call(name, args=None, call_id="c1"):
    return get_function_tool_call(name, json.dumps(args or {}), call_id=call_id)


def make(model, tools=(), **kwargs):
    agent = Agent(name="jarvis", instructions="You are a test.", model=model, tools=list(tools))
    return Runtime(agent, **kwargs)


async def run(runtime, text):
    return [e async for e in runtime.run(text)]


def of(events, kind):
    return [e for e in events if isinstance(e, kind)]


def finished(events):
    return of(events, RunFinished)[-1].reason


def text_of(events):
    return "".join(e.delta for e in of(events, TextMessageContent))


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_answer(self):
        rt = make(turns(get_text_message("Hello there")))
        events = await run(rt, "hi")
        self.assertIsInstance(events[0], RunStarted)
        self.assertEqual(len(of(events, StepStarted)), 1)
        self.assertEqual(text_of(events), "Hello there")
        self.assertEqual((len(of(events, TextMessageStart)), len(of(events, TextMessageEnd))), (1, 1))
        usage = [e for e in of(events, Custom) if e.name == "usage"]
        self.assertEqual(usage[0].value["requests"], 1)
        self.assertEqual(finished(events), "done")
        self.assertFalse(rt.running)
        roles = [i.get("role") for i in rt.session.items()]
        self.assertEqual(roles, ["user", "assistant"])

    async def test_tool_round_trip_with_ui_details(self):
        model = turns(call("get_weather", {"city": "Paris"}, "w1"), get_text_message("18°C in Paris."))
        rt = make(model, [get_weather])
        events = await run(rt, "weather in paris?")

        self.assertEqual([e.name for e in of(events, ToolCallStart)], ["get_weather"])
        self.assertEqual(json.loads(of(events, ToolCallArgs)[0].delta), {"city": "Paris"})
        result = of(events, ToolCallResult)[0]
        self.assertEqual((result.tool_call_id, result.name, result.content), ("w1", "get_weather", "Paris: 18°C"))
        self.assertEqual(result.details["props"]["temp_c"], 18)
        self.assertIsNone(result.error)
        self.assertEqual(len(of(events, StepStarted)), 2)

        sent = [i for i in model.last_turn_args["input"] if i.get("type") == "function_call_output"]
        self.assertEqual(sent[0]["output"], "Paris: 18°C")
        self.assertNotIn(CUSTOM_DATA_KEY, sent[0])
        self.assertEqual(rt.session.ui_details(), {"w1": {"type": "weather", "city": "Paris", "temp_c": 18}})

    async def test_errors_are_labelled_and_the_run_continues(self):
        model = turns(
            [call("get_weather", {"town": "Paris"}, "a"), call("broken", {}, "b"), call("teleport", {}, "c")],
            get_text_message("Sorry."),
        )
        rt = make(model, [get_weather, broken])
        events = await run(rt, "go")
        self.assertEqual([r.error for r in of(events, ToolCallResult)], ["invalid_args", "exception", "unknown_tool"])
        self.assertEqual(finished(events), "done")

    async def test_message_sent_mid_run_is_delivered_after_the_tool(self):
        holder = {}

        @tool
        def check_inbox() -> str:
            """Check the inbox."""
            holder["rt"].send("also, weather in Oslo?")
            return "No new mail."

        model = turns(call("check_inbox", {}, "i1"), get_text_message("No mail; Oslo is 18°C."))
        rt = make(model, [check_inbox])
        holder["rt"] = rt
        events = await run(rt, "check my inbox")

        injected = [e.value for e in of(events, Custom) if e.name == "message_injected"]
        self.assertEqual(injected, ["also, weather in Oslo?"])
        last_input = model.last_turn_args["input"]
        self.assertEqual(last_input[-2]["type"], "function_call_output")
        self.assertEqual(last_input[-1], {"role": "user", "content": "also, weather in Oslo?"})
        users = [i["content"] for i in rt.session.items() if i.get("role") == "user"]
        self.assertEqual(users, ["check my inbox", "also, weather in Oslo?"])

    async def test_message_sent_after_last_turn_starts_a_follow_up_run(self):
        holder = {}

        class SendAtEnd(AgentHooks):
            async def on_end(self, context, agent, output):
                if not holder.get("sent"):
                    holder["sent"] = True
                    holder["rt"].send("one more thing")

        model = turns(get_text_message("First."), get_text_message("Second."))
        agent = Agent(name="jarvis", model=model, hooks=SendAtEnd())
        rt = Runtime(agent)
        holder["rt"] = rt
        events = await run(rt, "question")
        self.assertEqual(text_of(events), "First.Second.")
        self.assertEqual(len(of(events, RunFinished)), 1)
        users = [i["content"] for i in rt.session.items() if i.get("role") == "user"]
        self.assertEqual(users, ["question", "one more thing"])

    async def test_abort_during_tool(self):
        rt = make(turns(call("slow_task", {}, "s1"), get_text_message("never")), [slow_task])
        asyncio.get_running_loop().call_later(0.1, rt.abort)
        start = time.perf_counter()
        events = await run(rt, "do it")
        self.assertLess(time.perf_counter() - start, 5)
        self.assertEqual(finished(events), "aborted")
        self.assertFalse(rt.running)

    async def test_max_turns(self):
        model = turns(*[call("get_weather", {"city": c}, f"c{i}") for i, c in enumerate("ABC")])
        rt = make(model, [get_weather], max_turns=2)
        self.assertEqual(finished(await run(rt, "loop")), "max_turns")

    async def test_model_error_reports_error(self):
        model = FakeModel()
        model.set_next_output(ConnectionError("ollama is down"))
        events = await run(make(model), "hi")
        self.assertIn("ollama is down", of(events, RunError)[0].message)
        self.assertEqual(finished(events), "error")

    async def test_session_persists_and_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.jsonl"
            rt = make(turns(call("get_weather", {"city": "Paris"}, "w1"), get_text_message("18°C.")),
                      [get_weather], session=Session(path))
            await run(rt, "weather?")
            model = turns(get_text_message("You asked about Paris."))
            await run(make(model, [get_weather], session=Session(path)), "what did I ask?")
            sent = model.last_turn_args["input"]
            kinds = [i.get("role") or i.get("type") for i in sent]
            self.assertEqual(kinds, ["user", "function_call", "function_call_output", "assistant", "user"])


if __name__ == "__main__":
    unittest.main()
