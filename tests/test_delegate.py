import json
import unittest

from agents import Agent

from omen.core import Runtime, ToolResult, delegate_tool, tool
from omen.core.delegate import fork_history
from omen.core.events import SubagentEvent, TextMessageContent, ToolCallResult, ToolCallStart
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message


@tool
def search_notes(query: str) -> ToolResult:
    """Search notes.

    Args:
        query: Keywords.
    """
    return ToolResult("Wi-Fi password: pinecone-42", details={"type": "notes", "hits": 1})


def turns(*outputs):
    model = FakeModel()
    model.add_multiple_turn_outputs([o if isinstance(o, list) else [o] for o in outputs])
    return model


def delegate_call(args: dict, call_id: str = "d1"):
    return get_function_tool_call("delegate", json.dumps(args), call_id=call_id)


def contents(items):
    return [i.get("content") if i.get("role") else i.get("type") for i in items]


class DelegateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.persona_model = turns(
            get_function_tool_call("search_notes", json.dumps({"query": "wifi"}), call_id="p1"),
            get_text_message("The cabin Wi-Fi password is pinecone-42."),
        )
        self.researcher = Agent(
            name="researcher",
            handoff_description="Looks things up in notes and on the web.",
            instructions="You research.",
            model=self.persona_model,
            tools=[search_notes],
        )

    def main_runtime(self, delegate_args: dict) -> tuple[Runtime, FakeModel]:
        main_model = turns(
            [get_text_message("Let me check."), delegate_call(delegate_args)],
            get_text_message("It's pinecone-42."),
        )
        main = Agent(name="jarvis", model=main_model, tools=[delegate_tool([self.researcher])])
        return Runtime(main), main_model

    async def test_delegate_without_context_sends_only_the_task(self):
        rt, main_model = self.main_runtime({"persona": "researcher", "task": "Find the cabin wifi password."})
        events = [e async for e in rt.run("What's the cabin wifi password?")]

        first_persona_input = self.persona_model.first_turn_args["input"]
        self.assertEqual(len(first_persona_input), 1)
        self.assertIn("Find the cabin wifi password.", first_persona_input[0]["content"])

        result = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"][0]
        self.assertEqual(result.content, "The cabin Wi-Fi password is pinecone-42.")
        self.assertEqual(result.details["props"]["persona"], "researcher")
        self.assertFalse(result.details["props"]["shared_context"])
        self.assertEqual(result.details["props"]["steps"], 2)

        # The persona's run streams to the UI, nested under the delegate call.
        nested = [e for e in events if isinstance(e, SubagentEvent)]
        self.assertTrue(all(e.tool_call_id == "d1" and e.persona == "researcher" for e in nested))
        self.assertIn("search_notes", [e.event.name for e in nested if isinstance(e.event, ToolCallStart)])
        self.assertIn("pinecone-42", "".join(e.event.delta for e in nested if isinstance(e.event, TextMessageContent)))

        # The main agent only gets the result, not the persona's run.
        main_items = rt.session.items()
        self.assertNotIn("search_notes", json.dumps(main_items))
        output = [i for i in main_items if i.get("type") == "function_call_output"][0]
        self.assertEqual(output["output"], "The cabin Wi-Fi password is pinecone-42.")

        # The persona's run is kept as a detached branch.
        branch = rt.session.items(result.details["props"]["branch"])
        self.assertIn("search_notes", json.dumps(branch))
        self.assertEqual(rt.session.items(), main_items)

    async def test_delegate_with_context_forks_the_conversation(self):
        rt, _ = self.main_runtime({"persona": "researcher", "task": "Find it.", "share_context": True})
        events = [e async for e in rt.run("What's the cabin wifi password?")]

        persona_input = self.persona_model.first_turn_args["input"]
        self.assertEqual(persona_input[0], {"role": "user", "content": "What's the cabin wifi password?"})
        self.assertEqual(persona_input[1].get("role"), "assistant")  # "Let me check." from the same response
        self.assertIn("Find it.", persona_input[-1]["content"])
        self.assertNotIn("function_call", [i.get("type") for i in persona_input])  # in-flight call excluded

        result = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"][0]
        self.assertTrue(result.details["props"]["shared_context"])

    async def test_string_boolean_is_accepted(self):
        rt, _ = self.main_runtime({"persona": "researcher", "task": "Find it.", "share_context": "true"})
        [e async for e in rt.run("q?")]
        self.assertGreater(len(self.persona_model.first_turn_args["input"]), 1)

    async def test_unknown_persona_is_an_actionable_error(self):
        rt, _ = self.main_runtime({"persona": "chef", "task": "cook"})
        events = [e async for e in rt.run("q?")]
        result = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"][0]
        self.assertEqual(result.error, "invalid_args")
        self.assertIn("researcher", result.content)

    def test_schema_lists_personas(self):
        t = delegate_tool([self.researcher])
        self.assertEqual(t.params_json_schema["properties"]["persona"]["enum"], ["researcher"])
        self.assertIn("Looks things up", t.description)
        self.assertEqual(t.params_json_schema["required"], ["persona", "task"])


class ForkHistoryTests(unittest.TestCase):
    def test_trims_from_a_user_message(self):
        items = [
            {"role": "user", "content": "q1"},
            {"type": "function_call", "call_id": "a"},
            {"type": "function_call_output", "call_id": "a"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]
        self.assertEqual(fork_history(items), items)
        self.assertEqual(contents(fork_history(items, 3)), ["q2", "a2"])
        self.assertEqual(fork_history(items, 1), [])


if __name__ == "__main__":
    unittest.main()
