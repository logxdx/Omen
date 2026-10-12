import json
import tempfile
import unittest
from pathlib import Path

from agents import Agent

from omen.core import Runtime, Session
from omen.core.compaction import Compactor, condense, render, split_point
from omen.core.events import Custom
from omen.ui.history import history
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message


def user(text):
    return {"role": "user", "content": text}


def reply(text):
    return {"role": "assistant", "type": "message", "content": [{"type": "output_text", "text": text}]}


def call(name, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name, "arguments": "{}"}


def output(call_id, text):
    return {"type": "function_call_output", "call_id": call_id, "output": text}


CONVERSATION = [
    user("first question " + "a" * 400), call("search", "c1"), output("c1", "r" * 2000), reply("first answer"),
    user("second question"), reply("second answer"),
    user("third question"), call("search", "c2"), output("c2", "result two"), reply("third answer"),
]


def summarizer(text="## Goal\n- answer the user's three questions about search results"):
    calls = []

    async def complete(messages):
        calls.append(messages)
        return text

    return complete, calls


class SplitTests(unittest.TestCase):
    def test_cuts_only_at_user_messages_and_keeps_the_last_turn(self):
        self.assertEqual(split_point(CONVERSATION, keep_recent_tokens=10), 6)  # just the last turn
        self.assertEqual(split_point(CONVERSATION, keep_recent_tokens=200), 4)  # last two turns fit
        self.assertEqual(split_point(CONVERSATION, keep_recent_tokens=100_000), 0)  # everything fits
        self.assertEqual(split_point([user("only"), reply("one")], 10), 0)

    def test_render_drops_context_blocks_and_cuts_tool_output(self):
        text = render([user("<context>\nNow: Monday\n</context>\n\nhi"), call("search", "c1"), output("c1", "x" * 900)])
        self.assertNotIn("Monday", text)
        self.assertIn("User: hi", text)
        self.assertIn("Assistant called search({})", text)
        self.assertIn("[300 more characters]", text)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_compaction_changes_the_model_view_not_the_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Session(Path(tmp) / "s.jsonl")
            await session.add_items(CONVERSATION)
            complete, calls = summarizer()
            info = await Compactor(trigger_tokens=1, keep_recent_tokens=10, complete=complete).maybe_compact(session, {})
            self.assertEqual((info["summarized_items"], info["kept_items"]), (6, 4))
            self.assertIn("first question", calls[0][1]["content"])

            items = session.items()
            self.assertEqual(len(items), 4)
            self.assertTrue(items[0]["content"].startswith("<summary>"))
            self.assertIn("## Goal", items[0]["content"])
            self.assertTrue(items[0]["content"].endswith("third question"))
            self.assertNotIn("first question", json.dumps(items))

            roles = [m["role"] for m in history(session)]
            self.assertIn("compaction", roles)
            self.assertEqual(roles.count("user"), 3)  # the UIs still show everything

            reopened = Session(Path(tmp) / "s.jsonl")
            self.assertEqual(reopened.items(), items)

    async def test_a_second_compaction_summarizes_the_first_summary(self):
        session = Session()
        await session.add_items(CONVERSATION)
        complete, calls = summarizer("## Goal\n- SUMMARY ONE: the first three questions were answered")
        compactor = Compactor(trigger_tokens=1, keep_recent_tokens=10, complete=complete)
        await compactor.maybe_compact(session, {})
        await session.add_items([reply("more"), user("fourth question"), reply("fourth answer")])
        compactor.complete, calls = summarizer("## Goal\n- SUMMARY TWO: four questions answered so far")
        await compactor.maybe_compact(session, {})
        self.assertIn("SUMMARY ONE", calls[0][1]["content"])  # merged, not lost
        items = session.items()
        self.assertIn("SUMMARY TWO", items[0]["content"])
        self.assertNotIn("SUMMARY ONE", json.dumps(items))
        self.assertTrue(items[0]["content"].endswith("fourth question"))

    async def test_under_budget_or_failed_summary_leaves_the_session_alone(self):
        session = Session()
        await session.add_items(CONVERSATION)
        complete, calls = summarizer()
        self.assertIsNone(await Compactor(trigger_tokens=10**6, complete=complete).maybe_compact(session, {}))
        self.assertEqual(calls, [])

        async def down(messages):
            raise ConnectionError("model down")

        self.assertIsNone(await Compactor(trigger_tokens=1, keep_recent_tokens=10, complete=down).maybe_compact(session, {}))
        self.assertEqual(session.items(), CONVERSATION)

        # Seen live: a small model echoed the template's headings with nothing under them.
        echoed, _ = summarizer("## Goal\n## Constraints and preferences\n## Progress\n- none\n## Files touched")
        self.assertIsNone(await Compactor(trigger_tokens=1, keep_recent_tokens=10, complete=echoed).maybe_compact(session, {}))
        self.assertEqual(session.items(), CONVERSATION)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def runtime(self, complete, trigger=1):
        self.model = FakeModel()
        compactor = Compactor(trigger_tokens=trigger, keep_recent_tokens=10, complete=complete)
        return Runtime(Agent(name="a", model=self.model), compactor=compactor)

    async def test_compacts_before_a_message_when_over_budget(self):
        complete, _ = summarizer("## Constraints and preferences\n- the user's code word is heron; keep it secret")
        rt = self.runtime(complete)
        self.model.add_multiple_turn_outputs([[get_text_message("one")], [get_text_message("two")], [get_text_message("three")]])
        [e async for e in rt.run("the code word is heron")]  # one turn: nothing to compact yet
        rt.state["memory_shown"] = ["m1"]
        [e async for e in rt.run("second message")]
        events = [e async for e in rt.run("what was the code word?")]
        compacted = [e for e in events if isinstance(e, Custom) and e.name == "compacted"]
        self.assertTrue(compacted)
        sent = json.dumps(self.model.last_turn_args["input"])
        self.assertIn("heron", sent)  # via the summary
        self.assertNotIn("the code word is heron", sent)  # the original turn is summarized away
        self.assertNotIn("memory_shown", rt.state)  # memories get shown again after the cut

    async def test_tool_calls_stay_with_their_results(self):
        complete, _ = summarizer()
        rt = self.runtime(complete)

        from omen.core import tool

        @tool
        def ping() -> str:
            """Ping."""
            return "pong"

        rt.agent.tools = [ping]
        self.model.add_multiple_turn_outputs([
            [get_function_tool_call("ping", "{}", call_id="p1")], [get_text_message("ok")],
            [get_text_message("two")], [get_text_message("three")],
        ])
        for text in ("ping it", "again", "and again"):
            [e async for e in rt.run(text)]
        items = self.model.last_turn_args["input"]
        call_ids = {i.get("call_id") for i in items if isinstance(i, dict) and i.get("type") == "function_call"}
        output_ids = {i.get("call_id") for i in items if isinstance(i, dict) and i.get("type") == "function_call_output"}
        self.assertEqual(call_ids, output_ids)

    async def test_manual_compact(self):
        complete, calls = summarizer()
        rt = self.runtime(complete, trigger=10**6)
        self.model.add_multiple_turn_outputs([[get_text_message("one")], [get_text_message("two")]])
        [e async for e in rt.run("first")]
        self.assertIsNone(await rt.compact())  # one turn: nothing to summarize
        [e async for e in rt.run("second")]
        info = await rt.compact()
        self.assertEqual(info["method"], "condensed")  # the old turn fits verbatim: no model call
        self.assertEqual(calls, [])


class CondenseTests(unittest.IsolatedAsyncioTestCase):
    def test_requests_and_answers_verbatim_tool_calls_as_one_line(self):
        text = condense(CONVERSATION[:6])
        self.assertEqual(text, (
            "User: first question " + "a" * 400 + "\n\n[1 tool call: search]\n\nAssistant: first answer"
            "\n\nUser: second question\n\nAssistant: second answer"
        ))
        self.assertNotIn("rrrr", text)  # tool output is dropped

    async def test_old_turns_kept_verbatim_without_a_model_call_when_they_fit(self):
        session = Session()
        await session.add_items(CONVERSATION)
        complete, calls = summarizer()
        compactor = Compactor(trigger_tokens=1, keep_recent_tokens=10, condensed_tokens=2000, complete=complete)
        info = await compactor.maybe_compact(session, {})
        self.assertEqual((info["method"], calls), ("condensed", []))
        first = session.items()[0]["content"]
        self.assertIn("User: second question", first)
        self.assertIn("[1 tool call: search]", first)
        self.assertTrue(first.endswith("third question"))

    async def test_only_the_oldest_turns_go_to_the_model(self):
        session = Session()
        await session.add_items(CONVERSATION)
        complete, calls = summarizer()
        compactor = Compactor(trigger_tokens=1, keep_recent_tokens=10, condensed_tokens=20, complete=complete)
        info = await compactor.maybe_compact(session, {})
        self.assertEqual(info["method"], "summarized")
        self.assertIn("first question", calls[0][1]["content"])  # the oldest turn is summarized
        self.assertNotIn("second question", calls[0][1]["content"])
        self.assertIn("## Earlier turns, word for word (tool calls shortened)\nUser: second question", info["summary"])


if __name__ == "__main__":
    unittest.main()
