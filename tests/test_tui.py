import asyncio
import json
import tempfile
import unittest
from pathlib import Path

try:
    from textual.widgets import Collapsible, DataTable, Input, Markdown, OptionList

    from omen.tui.app import BranchTree, Note, OmenApp, Question, UserMessage
    from omen.tui.render import RENDERERS, render

    HAVE_TEXTUAL = True
except ImportError:  # textual not installed yet (uv sync)
    HAVE_TEXTUAL = False

from omen.assistant import build_assistant
from omen.core import Session
from omen.ui.extract import Extractor
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message
from tests.test_skills import make_skill

SAMPLES = {
    "weather": {"place": "Pune", "temp_c": 26, "condition": "Cloudy", "feels_like_c": 27, "humidity": 51,
                "forecast": [{"date": "2026-10-12", "min_c": 21, "max_c": 33}]},
    "link_preview": {"url": "https://a.org", "title": "A", "description": "About [a]"},
    "search_results": {"query": "q", "results": [{"title": "T", "link": "https://t.org", "snippet": "s"}]},
    "video_results": {"query": "q", "results": [{"title": "V", "url": "u", "channel": "c", "duration": "1:00"}]},
    "file": {"path": "notes/a.md", "start": 1, "end": 2, "total_lines": 2},
    "file_list": {"path": ".", "entries": ["notes/", "a.md"]},
    "file_write": {"path": "a.md", "created": True},
    "file_delete": {"path": "a.md"},
    "diff": {"path": "a.md", "before": "- call Anna", "after": "- call Anna at 6"},
    "grep": {"pattern": "anna", "matches": ["a.md:1: call Anna"]},
    "choice": {"question": "Tea?", "options": ["tea", "coffee"], "answer": "tea"},
    "delegation": {"persona": "writer", "task": "draft", "shared_context": True, "steps": 2},
    "memory_saved": {"fact": "Likes tea."},
    "skill_loaded": {"skill": "web"},
    "download": {"kind": "audio", "url": "https://v"},
    "table": {"columns": ["A", "B"], "rows": [["1", "2"]]},
    "chart": {"title": "Steps", "kind": "bar", "labels": ["Mon", "Tue"], "values": [6200.0, 8900.0]},
    "card": {"title": "Pune", "body": "A city.", "url": "https://pune.example"},
}


@unittest.skipUnless(HAVE_TEXTUAL, "textual not installed")
class RendererTests(unittest.TestCase):
    def test_every_component_type_has_a_renderer(self):
        from omen.ui.components import TYPES

        self.assertEqual(set(RENDERERS), set(TYPES))

    def test_renderers_build_widgets(self):
        for kind, props in SAMPLES.items():
            widget = render({"type": kind, "valid": True, "props": props, "text": f"{kind} text"})
            self.assertIsNotNone(widget, kind)
            self.assertTrue(widget.has_class("component"), kind)
        self.assertIsInstance(render({"type": "table", "valid": True, "props": SAMPLES["table"], "text": ""}), DataTable)

    def test_fallbacks(self):
        self.assertIsInstance(render({"type": "mystery", "valid": False, "props": {}, "text": "plain"}), Markdown)
        self.assertIsInstance(render({"type": "weather", "valid": True, "props": {"oops": 1}, "text": "t"}), Markdown)
        self.assertIsNone(render(None))


@unittest.skipUnless(HAVE_TEXTUAL, "textual not installed")
class AppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        make_skill(self.root / "skills", "alpha", ["alpha"], tool_name="use_alpha")
        self.model = FakeModel()

    def tearDown(self):
        self.dir.cleanup()

    def app(self, session: Session | None = None) -> "OmenApp":
        def factory(persona=None, use_router=True):
            return build_assistant(
                persona=persona, model=self.model, skills_dirs=[self.root / "skills"],
                personas_dirs=[], memory_path=self.root / "m.jsonl", use_router=use_router,
            )

        async def no_llm(messages, schema):
            return "{}"

        return OmenApp(
            assistant_factory=factory, session=session or Session(self.root / "s.jsonl"),
            extractor=Extractor(complete=no_llm),
        )

    async def submit(self, pilot, app, text: str) -> None:
        prompt = app.query_one("#prompt", Input)
        prompt.value = text
        await pilot.press("enter")
        for _ in range(100):
            await pilot.pause(0.02)
            if not app.runtime.running and not app.workers:
                break

    async def test_conversation_with_tools_components_and_table(self):
        self.model.add_multiple_turn_outputs([
            [get_function_tool_call("load_skill", json.dumps({"name": "alpha"}), call_id="l1")],
            [get_function_tool_call("use_alpha", json.dumps({"thing": "x"}), call_id="a1")],
            [get_text_message("Done.\n\n| A | B |\n|---|---|\n| 1 | 2 |")],
        ])
        app = self.app()
        async with app.run_test() as pilot:
            await self.submit(pilot, app, "use alpha please")
            users = [str(w.render()) for w in app.query(UserMessage)]
            self.assertEqual(users, ["› use alpha please"])
            titles = [str(c.title) for c in app.query(Collapsible) if c.has_class("tool")]
            self.assertEqual(titles, ["✓ load_skill", "✓ use_alpha"])
            self.assertFalse(app.query(DataTable))  # the reply's markdown already shows the table
            self.assertIn("alpha", app.query_one("#header").render().plain)

    async def test_question_answered_by_picking_an_option(self):
        self.model.add_multiple_turn_outputs([
            [get_function_tool_call("ask_user", json.dumps({"question": "Tea or coffee?", "options": ["tea", "coffee"]}), call_id="q1")],
            [get_text_message("Tea it is.")],
        ])
        app = self.app()
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "order a drink"
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if app.query(Question):
                    break
            options = app.query_one(Question).query_one(OptionList)
            options.highlighted = 0
            options.action_select()
            for _ in range(100):
                await pilot.pause(0.02)
                if not app.runtime.running:
                    break
            self.assertFalse(app.query(Question))
            notes = [str(n.render()) for n in app.query(Note)]
            self.assertIn("› tea", notes)

    async def test_slash_commands_and_replay(self):
        self.model.add_multiple_turn_outputs([[get_text_message("Hello!")]])
        session = Session(self.root / "s.jsonl")
        app = self.app(session)
        async with app.run_test() as pilot:
            await self.submit(pilot, app, "hi")
            await self.submit(pilot, app, "/skill alpha")
            await self.submit(pilot, app, "/bogus")
            notes = " | ".join(str(n.render()) for n in app.query(Note))
            self.assertIn("⚙ skill: alpha", notes)

        replayed = self.app(Session(self.root / "s.jsonl"))
        async with replayed.run_test() as pilot:
            await pilot.pause(0.05)
            self.assertEqual([str(w.render()) for w in replayed.query(UserMessage)], ["› hi"])

    async def test_branch_tree_continues_from_an_earlier_point(self):
        self.model.add_multiple_turn_outputs([[get_text_message("First answer.")], [get_text_message("Second answer.")]])
        app = self.app()
        async with app.run_test() as pilot:
            await self.submit(pilot, app, "one")
            first_answer = app.session.leaf
            await self.submit(pilot, app, "two")
            app.action_tree()
            await pilot.pause(0.05)
            self.assertIsInstance(app.screen, BranchTree)
            app.screen.dismiss(first_answer)
            await pilot.pause(0.1)
            self.assertEqual(app.session.leaf, first_answer)
            self.assertEqual([str(w.render()) for w in app.query(UserMessage)], ["› one"])

    async def test_escape_stops_a_run(self):
        from tests.test_runtime import slow_task

        assistant_tools = None
        self.model.add_multiple_turn_outputs([[get_function_tool_call("slow_task", "{}", call_id="s1")]])
        app = self.app()
        app.runtime.agent.tools.append(slow_task)
        async with app.run_test() as pilot:
            app.query_one("#prompt", Input).value = "go"
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.02)
                if app.runtime.running:
                    break
            await pilot.press("escape")
            for _ in range(100):
                await pilot.pause(0.02)
                if not app.runtime.running:
                    break
            self.assertFalse(app.runtime.running)
            self.assertIn("[aborted]", " ".join(str(n.render()) for n in app.query(Note)))

    async def test_subagent_block_collapses_and_summary_follows_it(self):
        from omen.core import events as om

        app = self.app()
        async with app.run_test() as pilot:
            t = app.transcript
            ui = {"type": "delegation", "valid": True, "props": {"persona": "writer", "task": "draft"}, "text": "x"}
            for e in [
                om.ToolCallStart("d1", "delegate"),
                om.SubagentEvent("d1", "writer", om.TextMessageStart("s1")),
                om.SubagentEvent("d1", "writer", om.TextMessageContent("s1", "Hi Priya")),
                om.SubagentEvent("d1", "writer", om.TextMessageEnd("s1", "Hi Priya")),
                om.ToolCallResult("d1", "delegate", "Hi Priya", ui, None),
            ]:
                await t.handle(e)
            await pilot.pause(0.05)
            block = t.subagent_blocks["d1"]
            self.assertTrue(block.collapsed)
            siblings = list(app.query_one("#transcript").children)
            self.assertTrue(siblings[siblings.index(block) + 1].has_class("component"))


if __name__ == "__main__":
    unittest.main()
