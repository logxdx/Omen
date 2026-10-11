import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from omen.core import Agent, Session, ToolContext, ToolRegistry, tool
from omen.core.events import (
    RunError,
    RunFinished,
    RunStarted,
    TextMessageContent,
    TextMessageEnd,
    TextMessageStart,
    ToolCallResult,
)
from tests.fakes import HANG, FakeLLM


@tool
def get_weather(city: str) -> str:
    """Current weather for a city.

    Args:
        city: City name.
    """
    return f"{city}: 18°C"


@tool
def check_inbox(ctx: ToolContext) -> str:
    """Check the inbox."""
    ctx.agent.steer("Also, what's the weather in Oslo?")
    return "No new mail."


@tool
async def slow_task() -> str:
    """Takes forever."""
    await asyncio.sleep(60)
    return "done"


def make(turns, *, delay=0.0, **kwargs):
    llm = FakeLLM(turns, delay=delay)
    agent = Agent(llm, ToolRegistry([get_weather, check_inbox, slow_task]), "You are a test.", **kwargs)
    return agent, llm


async def run(agent, text):
    return [e async for e in agent.run(text)]


def results(events):
    return [e for e in events if isinstance(e, ToolCallResult)]


def finished(events):
    return [e for e in events if isinstance(e, RunFinished)][-1].reason


class LoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_answer(self):
        agent, llm = make(["Hello there"])
        events = await run(agent, "hi")
        self.assertIsInstance(events[0], RunStarted)
        self.assertEqual("".join(e.delta for e in events if isinstance(e, TextMessageContent)), "Hello there")
        self.assertEqual(sum(isinstance(e, TextMessageStart) for e in events), 1)
        self.assertEqual(sum(isinstance(e, TextMessageEnd) for e in events), 1)
        self.assertEqual(finished(events), "done")
        self.assertEqual(agent.messages, [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello there"},
        ])
        self.assertEqual(llm.requests[0]["messages"][0], {"role": "system", "content": "You are a test."})

    async def test_tool_round_trip(self):
        agent, llm = make([[("get_weather", {"city": "Paris"})], "It's 18°C in Paris."])
        events = await run(agent, "weather in paris?")
        self.assertEqual([r.content for r in results(events)], ["Paris: 18°C"])
        self.assertEqual([m["role"] for m in agent.messages], ["user", "assistant", "tool", "assistant"])
        call_id = agent.messages[1]["tool_calls"][0]["id"]
        self.assertEqual(agent.messages[2]["tool_call_id"], call_id)
        self.assertEqual(llm.requests[1]["messages"][-1]["content"], "Paris: 18°C")
        self.assertEqual(finished(events), "done")

    async def test_invalid_args_then_recovery(self):
        agent, _ = make([[("get_weather", {})], [("get_weather", {"city": "Paris"})], "18°C"])
        events = await run(agent, "weather?")
        first, second = results(events)
        self.assertEqual(first.error, "invalid_args")
        self.assertIn("city", first.content)
        self.assertIsNone(second.error)
        self.assertEqual(finished(events), "done")

    async def test_fuzzy_and_unknown_tool_names(self):
        agent, _ = make([[("getWeather", {"city": "Rome"}), ("teleport", {})], "ok"])
        fuzzy, unknown = results(await run(agent, "go"))
        self.assertEqual((fuzzy.name, fuzzy.error), ("get_weather", None))
        self.assertEqual(unknown.error, "unknown_tool")

    async def test_loop_guard_nudges_then_stops(self):
        same = [("get_weather", {"city": "Paris"})]
        agent, _ = make([same, same, same, "never reached"])
        events = await run(agent, "weather?")
        self.assertEqual([r.error for r in results(events)], [None, "loop", "loop"])
        self.assertIn("already made this exact call", results(events)[1].content)
        self.assertEqual(finished(events), "loop")

    async def test_max_turns(self):
        turns = [[("get_weather", {"city": c})] for c in ("A", "B", "C")]
        agent, _ = make(turns, max_turns=2)
        events = await run(agent, "loop forever")
        self.assertEqual(finished(events), "max_turns")
        self.assertEqual(len(results(events)), 2)

    async def test_steering_injected_after_tool_batch(self):
        agent, llm = make([[("check_inbox", {})], "No mail, and Oslo is 18°C."])
        await run(agent, "check my inbox")
        second_request = llm.requests[1]["messages"]
        self.assertEqual(second_request[-2]["role"], "tool")
        self.assertEqual(second_request[-1], {"role": "user", "content": "Also, what's the weather in Oslo?"})

    async def test_follow_up_delivered_when_idle(self):
        agent, _ = make(["First answer.", "Second answer."])
        agent.follow_up("And another thing")
        events = await run(agent, "question")
        self.assertEqual([m["content"] for m in agent.messages],
                         ["question", "First answer.", "And another thing", "Second answer."])
        self.assertEqual(finished(events), "done")

    async def test_abort_while_waiting_for_first_token(self):
        agent, _ = make([HANG])
        asyncio.get_running_loop().call_later(0.05, agent.abort)
        start = time.perf_counter()
        events = await run(agent, "hi")
        self.assertLess(time.perf_counter() - start, 2)
        self.assertEqual(finished(events), "aborted")
        self.assertFalse(agent.running)

    async def test_abort_mid_stream_keeps_partial_text(self):
        agent, _ = make(["one two three four five six"], delay=0.05)

        async def consume():
            out = []
            async for e in agent.run("count"):
                out.append(e)
                if isinstance(e, TextMessageContent) and "two" in e.delta:
                    agent.abort()
            return out

        events = await consume()
        self.assertEqual(finished(events), "aborted")
        self.assertEqual(agent.messages[-1], {"role": "assistant", "content": "one two"})

    async def test_abort_during_tool_keeps_history_valid(self):
        agent, _ = make([[("slow_task", {})]])
        asyncio.get_running_loop().call_later(0.05, agent.abort)
        events = await run(agent, "do it")
        self.assertEqual([r.error for r in results(events)], ["aborted"])
        self.assertEqual([m["role"] for m in agent.messages], ["user", "assistant", "tool"])
        self.assertEqual(finished(events), "aborted")

    async def test_llm_exception_reports_error(self):
        agent, _ = make([ConnectionError("ollama is down")])
        events = await run(agent, "hi")
        errors = [e for e in events if isinstance(e, RunError)]
        self.assertIn("ollama is down", errors[0].message)
        self.assertEqual(finished(events), "error")
        self.assertFalse(agent.running)

    async def test_session_persists_and_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.jsonl"
            agent, _ = make([[("get_weather", {"city": "Paris"})], "18°C."], session=Session(path))
            await run(agent, "weather?")
            resumed, llm = make(["You asked about Paris."], session=Session(path))
            await run(resumed, "what did I ask?")
            sent = llm.requests[0]["messages"]
            self.assertEqual([m["role"] for m in sent], ["system", "user", "assistant", "tool", "assistant", "user"])

    async def test_system_prompt_callable_is_evaluated_each_step(self):
        calls = []

        def prompt():
            calls.append(1)
            return f"step {len(calls)}"

        llm = FakeLLM([[("get_weather", {"city": "Paris"})], "done"])
        agent = Agent(llm, ToolRegistry([get_weather]), prompt)
        await run(agent, "go")
        self.assertEqual([r["messages"][0]["content"] for r in llm.requests], ["step 1", "step 2"])


if __name__ == "__main__":
    unittest.main()
