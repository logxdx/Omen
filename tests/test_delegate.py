import json
import unittest

from agents import Agent

from omen.core import Runtime, ToolResult, delegate_tool, tool
from omen.core.delegate import delegation_result, fork_history, latest_thread, waiting_for_answer
from omen.core.session import CUSTOM_DATA_KEY
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

    async def test_follow_up_continues_the_personas_thread(self):
        self.persona_model.add_multiple_turn_outputs([[get_text_message("Also: dentist on Friday.")]])
        main_model = turns(
            delegate_call({"persona": "researcher", "task": "Find the cabin wifi password."}),
            get_text_message("It's pinecone-42."),
            delegate_call({"persona": "researcher", "task": "Anything else in there?", "follow_up": True}, "d2"),
            get_text_message("Dentist on Friday."),
        )
        rt = Runtime(Agent(name="jarvis", model=main_model, tools=[delegate_tool([self.researcher])]))
        [e async for e in rt.run("What's the cabin wifi password?")]
        events = [e async for e in rt.run("Ask it what else is in there.")]

        persona_input = self.persona_model.last_turn_args["input"]
        self.assertIn("Find the cabin wifi password.", persona_input[0]["content"])
        self.assertIn("search_notes", json.dumps(persona_input))  # its own earlier tool call and result
        self.assertIn("follow-up", persona_input[-1]["content"])
        self.assertIn("Anything else in there?", persona_input[-1]["content"])

        props = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"][0].details["props"]
        self.assertTrue(props["follow_up"])
        thread = rt.session.thread(props["branch"])  # one branch holds both runs
        self.assertEqual(contents(thread)[0], persona_input[0]["content"])
        self.assertIn("dentist on Friday", json.dumps(thread))
        self.assertNotIn("search_notes", json.dumps(rt.session.items()))  # main context unchanged

    async def test_follow_up_without_an_earlier_thread_starts_fresh(self):
        rt, _ = self.main_runtime({"persona": "researcher", "task": "Find it.", "follow_up": True})
        events = [e async for e in rt.run("q?")]
        self.assertEqual(len(self.persona_model.first_turn_args["input"]), 1)
        result = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"][0]
        self.assertFalse(result.details["props"]["follow_up"])

    async def test_named_delegation_continues_only_right_after_the_same_persona(self):
        self.persona_model.add_multiple_turn_outputs([
            [get_text_message("Shorter: pinecone-42.")],
            [get_text_message("Fresh answer.")],
        ])
        main_model = turns(get_text_message("You're welcome."))

        def prepare(text: str, state: dict) -> list:
            if text.startswith("ask"):
                state["pre_call"] = {
                    "name": "delegate",
                    "arguments": {"persona": "researcher", "task": text, "follow_up": "auto"},
                }
            return []

        rt = Runtime(
            Agent(name="jarvis", model=main_model, tools=[delegate_tool([self.researcher])]), prepare=prepare
        )
        inputs = []
        for text in ["ask the researcher for the wifi password", "ask the researcher to say it shorter",
                     "thanks", "ask the researcher about something else"]:
            [e async for e in rt.run(text)]
            inputs.append(self.persona_model.last_turn_args["input"])

        self.assertIn("follow-up", inputs[1][-1]["content"])  # right after the same persona
        self.assertIn("wifi password", json.dumps(inputs[1]))
        self.assertEqual(len(inputs[3]), 1)  # a turn in between: a fresh brief

    def asking_researcher(self) -> FakeModel:
        model = turns(
            get_function_tool_call("ask_superior", json.dumps({"question": "Which cabin?"}), call_id="q1"),
            get_text_message("The lake cabin's password is pinecone-42."),
        )
        self.researcher = Agent(name="researcher", instructions="You research.", model=model, tools=[search_notes])
        return model

    async def test_question_pauses_the_persona_and_the_answer_continues_it(self):
        persona_model = self.asking_researcher()
        main_model = turns(
            delegate_call({"persona": "researcher", "task": "Find the cabin wifi password."}),
            delegate_call({"persona": "researcher", "task": "The lake cabin."}, "d2"),  # no follow_up flag
            get_text_message("It's pinecone-42."),
        )
        tool = delegate_tool([self.researcher], auto_answer=False)  # the main model answers
        rt = Runtime(Agent(name="jarvis", model=main_model, tools=[tool]))
        events = [e async for e in rt.run("What's the cabin wifi password?")]

        asked, answered = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"]
        self.assertIn("researcher paused to ask: Which cabin?", asked.content)
        self.assertEqual(asked.details["props"]["question"], "Which cabin?")
        self.assertIsNone(asked.error)
        self.assertEqual(persona_model.first_turn_args["input"][0]["role"], "user")  # the run stopped at the question

        persona_input = persona_model.last_turn_args["input"]
        self.assertIn("Find the cabin wifi password.", persona_input[0]["content"])
        self.assertEqual([i.get("name") for i in persona_input if i.get("type") == "function_call"], ["ask_superior"])
        self.assertIn("answers your question", persona_input[-1]["content"])
        self.assertIn("The lake cabin.", persona_input[-1]["content"])
        self.assertTrue(answered.details["props"]["follow_up"])
        self.assertIsNone(answered.details["props"].get("question"))
        self.assertEqual(answered.content, "The lake cabin's password is pinecone-42.")
        self.assertIn("ask_superior", [t.name for t in persona_model.first_turn_args["tools"]])

    async def test_named_delegation_question_goes_to_the_main_model(self):
        self.asking_researcher()
        main_model = turns(get_text_message("The researcher asks: which cabin?"))

        def prepare(text: str, state: dict) -> list:
            state["pre_call"] = {"name": "delegate", "arguments": {"persona": "researcher", "task": text}}
            return []

        tool = delegate_tool([self.researcher], auto_answer=False)
        rt = Runtime(Agent(name="jarvis", model=main_model, tools=[tool]), prepare=prepare)
        events = [e async for e in rt.run("ask the researcher for the cabin wifi password")]

        main_input = json.dumps(main_model.last_turn_args["input"])
        self.assertIn("paused to ask: Which cabin?", main_input)  # not shown to the user as the reply
        reply = "".join(e.delta for e in events if isinstance(e, TextMessageContent))
        self.assertEqual(reply, "The researcher asks: which cabin?")

    async def test_question_is_answered_from_the_conversation_once(self):
        persona_model = self.asking_researcher()
        main_model = turns(
            get_text_message("Noted."),
            delegate_call({"persona": "researcher", "task": "Find the cabin wifi password."}),
            get_text_message("It's pinecone-42."),
        )
        rt = Runtime(Agent(name="jarvis", model=main_model, tools=[delegate_tool([self.researcher])]))
        [e async for e in rt.run("We're going to the lake cabin.")]
        events = [e async for e in rt.run("What's the wifi password there?")]

        persona_input = persona_model.last_turn_args["input"]
        self.assertEqual(persona_input[0]["content"], "We're going to the lake cabin.")  # the conversation, once
        self.assertEqual([i.get("name") for i in persona_input if i.get("type") == "function_call"], ["ask_superior"])
        self.assertIn("conversation above", persona_input[-1]["content"])

        result = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"][0]
        self.assertEqual(result.content, "The lake cabin's password is pinecone-42.")
        self.assertTrue(result.details["props"]["shared_context"])
        thread = json.dumps(rt.session.thread(result.details["props"]["branch"]))
        self.assertIn("ask_superior", thread)
        self.assertNotIn("We're going to the lake cabin.", thread)  # the shared conversation isn't stored twice

    def test_question_helpers(self):
        call = {"type": "function_call", "call_id": "q", "name": "ask_superior", "arguments": "{}"}
        out = {"type": "function_call_output", "call_id": "q", "output": "sent"}
        self.assertTrue(waiting_for_answer([{"role": "user", "content": "t"}, call, out]))
        self.assertFalse(waiting_for_answer([call, out, {"role": "assistant", "content": "done"}]))
        self.assertFalse(waiting_for_answer([{**call, "name": "search_notes"}, out]))
        self.assertIsNone(delegation_result({"type": "delegation", "question": "Which?"}, "x"))
        self.assertEqual(delegation_result({"type": "delegation", "result": "r"}, "x"), "r")

    def test_latest_thread_counts_user_messages_since(self):
        def output(persona, branch):
            return {"type": "function_call_output", CUSTOM_DATA_KEY: {"ui": {"type": "delegation", "persona": persona, "branch": branch}}}

        items = [{"role": "user", "content": "a"}, output("writer", "b1"), {"role": "user", "content": "b"},
                 output("researcher", "b2"), {"role": "user", "content": "c"}]
        self.assertEqual(latest_thread(items, "writer"), ("b1", 2))
        self.assertEqual(latest_thread(items, "researcher"), ("b2", 1))
        self.assertEqual(latest_thread(items, "chef"), (None, 3))

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
