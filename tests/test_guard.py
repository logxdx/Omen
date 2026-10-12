import json
import unittest

from agents import Agent

from omen.core import Runtime, tool
from omen.core.events import ToolCallResult
from omen.core.guard import guard_all
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message


class GuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.runs = []
        runs = self.runs

        @tool
        def lookup(query: str) -> str:
            """Look something up.

            Args:
                query: What to look up.
            """
            runs.append(query)
            return f"found {query}"

        self.lookup = lookup
        self.model = FakeModel()

    def runtime(self, every=0):
        agent = Agent(name="a", model=self.model, tools=guard_all([self.lookup], max_turns=50, every=every))
        return Runtime(agent)

    def call(self, query, call_id):
        return [get_function_tool_call("lookup", json.dumps({"query": query}), call_id=call_id)]

    async def results(self, rt, text):
        return [e.content for e in [e async for e in rt.run(text)] if isinstance(e, ToolCallResult)]

    async def test_an_identical_call_is_not_run_twice(self):
        self.model.add_multiple_turn_outputs([
            self.call("pune", "c1"), self.call("pune", "c2"), self.call("pune", "c3"), [get_text_message("done")],
        ])
        results = await self.results(self.runtime(), "look up pune")
        self.assertEqual(self.runs, ["pune"])
        self.assertEqual(results[0], "found pune")
        self.assertTrue(results[1].startswith("Not run: you just called lookup"))
        self.assertTrue(results[2].startswith("Not run again:"))

    async def test_different_arguments_and_new_turns_run(self):
        self.model.add_multiple_turn_outputs([
            self.call("pune", "c1"), self.call("delhi", "c2"), [get_text_message("ok")],
            self.call("delhi", "c3"), [get_text_message("ok again")],
        ])
        rt = self.runtime()
        await self.results(rt, "pune and delhi")
        await self.results(rt, "delhi again please")  # a new user turn: not a loop
        self.assertEqual(self.runs, ["pune", "delhi", "delhi"])

    async def test_goal_reminder_every_n_steps_is_stored_with_the_result(self):
        self.model.add_multiple_turn_outputs([
            self.call("a", "c1"), self.call("b", "c2"), self.call("c", "c3"), [get_text_message("ok")],
        ])
        rt = self.runtime(every=2)
        results = await self.results(rt, "<context>\nNow: Monday\n</context>\n\nfind a, b and c for me")
        self.assertEqual(results[0], "found a")
        self.assertEqual(results[1], "found b\n\n(goal: find a, b and c for me · step 2 of 50)")
        self.assertEqual(results[2], "found c")
        stored = [i["output"] for i in rt.session.items() if i.get("type") == "function_call_output"]
        self.assertIn("(goal: find a, b and c for me · step 2 of 50)", stored[1])  # append-only: it stays


if __name__ == "__main__":
    unittest.main()
