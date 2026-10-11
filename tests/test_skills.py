import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from omen.assistant import build_assistant
from omen.core import Runtime
from omen.core.events import Custom, ToolCallResult
from omen.core.skills import MAX_LOADED, Skills, loaded, parse_skill_md
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message


def make_skill(root: Path, name: str, keywords: list[str], body: str = "Do the thing.", tool_name: str | None = None):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: The {name} skill.\nkeywords: {json.dumps(keywords)}\n---\n{body}\n"
    )
    if tool_name:
        (folder / "helper.py").write_text(f"VALUE = '{name}-value'\n")
        (folder / "tools.py").write_text(textwrap.dedent(f"""
            from omen.core.tools import ToolResult, tool
            from .helper import VALUE

            @tool
            def {tool_name}(thing: str) -> ToolResult:
                '''Use the {name} skill.

                Args:
                    thing: What to use it on.
                '''
                return ToolResult(f"{{VALUE}}: {{thing}}", details={{"type": "{name}"}})

            TOOLS = [{tool_name}]
        """))


def tool_names(turn_args) -> list[str]:
    return [t.name for t in turn_args["tools"]]


class ParseTests(unittest.TestCase):
    def test_frontmatter_and_body(self):
        meta, body = parse_skill_md("---\nname: web\nkeywords: [a, b]\n---\n1. Search.\n")
        self.assertEqual(meta, {"name": "web", "keywords": ["a", "b"]})
        self.assertEqual(body, "1. Search.")

    def test_no_frontmatter(self):
        self.assertEqual(parse_skill_md("just text"), ({}, "just text"))


class SkillsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        make_skill(self.root, "alpha", ["alpha", "first letter"], body="Alpha steps.", tool_name="use_alpha")
        make_skill(self.root, "beta", ["beta"], tool_name="use_beta")
        make_skill(self.root, "notes", ["note"])  # instructions only

    def tearDown(self):
        self.dir.cleanup()

    def test_discovery_with_relative_imports(self):
        skills = Skills([self.root])
        self.assertEqual(set(skills.skills), {"alpha", "beta", "notes"})
        self.assertEqual([t.name for t in skills.skills["alpha"].tools], ["use_alpha"])
        self.assertEqual(skills.skills["notes"].tools, [])
        self.assertIn("- alpha: The alpha skill.", skills.roster())

    def test_router(self):
        skills = Skills([self.root])
        self.assertEqual(skills.route("tell me about alpha"), "alpha")
        self.assertEqual(skills.route("the first letter please"), "alpha")  # phrase keyword
        self.assertEqual(skills.route("BETA!"), "beta")
        self.assertIsNone(skills.route("nothing relevant"))

    def test_lru_cap(self):
        skills = Skills([self.root])
        state: dict = {}
        for name in ["alpha", "beta", "notes", "alpha"]:
            skills.load(name, state)
        self.assertEqual(loaded(state), ["beta", "notes", "alpha"])
        self.assertLessEqual(len(loaded(state)), MAX_LOADED)
        self.assertIsNone(skills.load("missing", state))

    async def test_tools_are_hidden_until_load_skill(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([
            [get_function_tool_call("load_skill", json.dumps({"name": "alpha"}), call_id="l1")],
            [get_function_tool_call("use_alpha", json.dumps({"thing": "x"}), call_id="u1")],
            [get_text_message("done")],
        ])
        assistant = build_assistant(model=model, skills_dirs=[self.root], personas_dirs=[], memory_path=self.root / "m.jsonl", use_router=False)
        rt = Runtime(assistant.agent, prepare=assistant.prepare)
        events = [e async for e in rt.run("do something")]

        first = tool_names(model.first_turn_args)
        self.assertEqual(first, ["load_skill", "remember", "ask_user"])
        self.assertIn("use_alpha", tool_names(model.last_turn_args))
        self.assertNotIn("use_beta", tool_names(model.last_turn_args))
        self.assertIn("Alpha steps.", model.last_turn_args["system_instructions"])
        self.assertNotIn("Alpha steps.", model.first_turn_args["system_instructions"])
        results = {e.name: e for e in events if isinstance(e, ToolCallResult)}
        self.assertEqual(results["use_alpha"].content, "alpha-value: x")
        self.assertEqual(loaded(rt.state), ["alpha"])  # stays loaded for the next message

    async def test_router_preloads_before_the_first_call(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([[get_text_message("ok")]])
        assistant = build_assistant(model=model, skills_dirs=[self.root], personas_dirs=[], memory_path=self.root / "m.jsonl")
        rt = Runtime(assistant.agent, prepare=assistant.prepare)
        events = [e async for e in rt.run("use beta on this")]
        self.assertIn("use_beta", tool_names(model.first_turn_args))
        routed = [e.value for e in events if isinstance(e, Custom) and e.name == "skill_loaded"]
        self.assertEqual(routed, [{"skill": "beta", "by": "router"}])

    async def test_unknown_skill_is_an_actionable_error(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([
            [get_function_tool_call("load_skill", json.dumps({"name": "gamma"}), call_id="l1")],
            [get_text_message("sorry")],
        ])
        assistant = build_assistant(model=model, skills_dirs=[self.root], personas_dirs=[], memory_path=self.root / "m.jsonl", use_router=False)
        events = [e async for e in Runtime(assistant.agent).run("x")]
        result = [e for e in events if isinstance(e, ToolCallResult)][0]
        self.assertEqual(result.error, "invalid_args")
        self.assertIn("alpha", result.content)

    def test_reload_picks_up_new_skills(self):
        assistant = build_assistant(model=FakeModel(), skills_dirs=[self.root], personas_dirs=[], memory_path=self.root / "m.jsonl")
        make_skill(self.root, "gamma", ["gamma"], tool_name="use_gamma")
        assistant.reload()
        self.assertIn("gamma", assistant.skills.skills)
        self.assertIn("use_gamma", [t.name for t in assistant.agent.tools])


if __name__ == "__main__":
    unittest.main()
