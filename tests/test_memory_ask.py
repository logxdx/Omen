import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from omen.assistant import build_assistant
from omen.core import Runtime
from omen.core.events import ToolCallResult, UserQuestion
from omen.core.memory import Memory
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.dir.name) / "facts.jsonl")

    def tearDown(self):
        self.dir.cleanup()

    def test_add_forget(self):
        a = self.memory.add("The user's sister is Anna.")
        self.memory.add("The user likes green tea.")
        self.assertTrue(self.memory.forget(a["id"]))
        self.assertFalse(self.memory.forget("nope"))
        self.assertEqual([f["fact"] for f in self.memory.facts()], ["The user likes green tea."])

    def test_recall_ranks_by_overlap_when_there_are_many(self):
        for i in range(8):
            self.memory.add(f"Unrelated fact number {i}.")
        self.memory.add("The user's sister Anna has a birthday on May 3.")
        recalled = [f["fact"] for f in self.memory.recall("when is my sister's birthday?")]
        self.assertEqual(recalled[0], "The user's sister Anna has a birthday on May 3.")
        self.assertIn("Things you know about the user:", self.memory.prompt_section("sister birthday"))

    def test_few_facts_are_all_recalled(self):
        self.memory.add("The user lives in Pune.")
        self.assertEqual(len(self.memory.recall("anything at all")), 1)


class AssistantMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_remember_then_recall_in_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "facts.jsonl"
            model = FakeModel()
            model.add_multiple_turn_outputs([
                [get_function_tool_call("remember", json.dumps({"fact": "The user's sister is Anna."}), call_id="r1")],
                [get_text_message("Noted.")],
                [get_text_message("Your sister is Anna.")],
            ])
            assistant = build_assistant(model=model, skills_dirs=[], personas_dirs=[], memory_path=path)
            rt = Runtime(assistant.agent, prepare=assistant.prepare)
            [e async for e in rt.run("My sister is called Anna.")]
            [e async for e in rt.run("What's my sister's name?")]
            self.assertIn("The user's sister is Anna.", model.last_turn_args["system_instructions"])


class AskUserTests(unittest.IsolatedAsyncioTestCase):
    def model(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([
            [get_function_tool_call("ask_user", json.dumps({"question": "Tea or coffee?", "options": ["tea", "coffee"]}), call_id="q1")],
            [get_text_message("Tea it is.")],
        ])
        return model

    async def test_question_waits_for_answer(self):
        model = self.model()
        assistant = build_assistant(model=model, skills_dirs=[], personas_dirs=[], memory_path=Path(tempfile.mkdtemp()) / "m.jsonl")
        rt = Runtime(assistant.agent)
        events = []
        async for event in rt.run("order me a drink"):
            events.append(event)
            if isinstance(event, UserQuestion):
                self.assertEqual(rt.pending_question, event)
                self.assertEqual(event.options, ["tea", "coffee"])
                asyncio.get_running_loop().call_later(0.01, rt.answer, "tea")
        result = [e for e in events if isinstance(e, ToolCallResult)][0]
        self.assertEqual(result.content, "The user answered: tea")
        self.assertEqual(result.details["answer"], "tea")
        self.assertIsNone(rt.pending_question)
        self.assertFalse(rt.answer("late"))

    async def test_ask_handler_answers_programmatically(self):
        model = self.model()

        async def handler(question, options):
            return options[1]

        assistant = build_assistant(model=model, skills_dirs=[], personas_dirs=[], memory_path=Path(tempfile.mkdtemp()) / "m.jsonl")
        events = [e async for e in Runtime(assistant.agent, ask_handler=handler).run("drink?")]
        self.assertFalse(any(isinstance(e, UserQuestion) for e in events))
        result = [e for e in events if isinstance(e, ToolCallResult)][0]
        self.assertEqual(result.content, "The user answered: coffee")


if __name__ == "__main__":
    unittest.main()
