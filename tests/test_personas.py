import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from omen.assistant import build_assistant
from omen.config import REPO_ROOT
from omen.core import Runtime
from omen.core.events import Custom, SubagentEvent, ToolCallResult
from omen.core.personas import discover
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message
from tests.test_skills import make_skill


def make_persona(root: Path, name: str, front: str, body: str = "") -> None:
    (root / f"{name}.md").write_text(f"---\nname: {name}\n{textwrap.dedent(front).strip()}\n---\n{body or f'You are {name}.'}\n")


def names(tools) -> list[str]:
    return [t.name for t in tools]


class DiscoverTests(unittest.TestCase):
    def test_fields_defaults_and_broken_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            make_persona(root, "boss", "description: Main voice.\ndelegate: false")
            make_persona(root, "helper", "description: Helps.\nskills: [alpha]\nmax_turns: 3\nmodel: openai/tiny")
            (root / "broken.md").write_text("---\ndescription: bad: yaml: here\n---\nx")
            personas = discover([root])
            self.assertEqual(set(personas), {"boss", "helper"})
            self.assertFalse(personas["boss"].delegate)
            self.assertTrue(personas["boss"].main)
            helper = personas["helper"]
            self.assertEqual((helper.skills, helper.max_turns, helper.model), (["alpha"], 3, "openai/tiny"))
            self.assertTrue(helper.delegate)

    def test_repo_personas(self):
        personas = discover([REPO_ROOT / "personas"])
        self.assertEqual(set(personas), {"omen", "researcher", "writer"})
        self.assertFalse(personas["omen"].delegate)
        self.assertEqual(personas["researcher"].skills, ["web"])


class AssistantPersonaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        self.skills_dir, self.personas_dir = root / "skills", root / "personas"
        self.personas_dir.mkdir()
        make_skill(self.skills_dir, "alpha", ["alpha"], body="Alpha steps.", tool_name="use_alpha")
        make_persona(self.personas_dir, "boss", "description: Main voice.\ndelegate: false", "You are Boss. Be brief.")
        make_persona(self.personas_dir, "helper", "description: Uses alpha.\nskills: [alpha]\nmax_turns: 2")
        make_persona(self.personas_dir, "quiet", "description: Main only.\ndelegate: false\nmain: true")
        self.memory = root / "m.jsonl"

    def tearDown(self):
        self.dir.cleanup()

    def build(self, model, persona="boss"):
        return build_assistant(
            persona=persona, model=model, skills_dirs=[self.skills_dir],
            personas_dirs=[self.personas_dir], memory_path=self.memory,
        )

    async def test_main_prompt_and_delegate_roster(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([[get_text_message("ok")]])
        assistant = self.build(model)
        self.assertEqual(assistant.agent.name, "boss")
        delegate = [t for t in assistant.core_tools if t.name == "delegate"][0]
        self.assertEqual(delegate.params_json_schema["properties"]["persona"]["enum"], ["helper"])
        [e async for e in Runtime(assistant.agent, prepare=assistant.prepare).run("hi")]
        prompt = model.first_turn_args["system_instructions"]
        self.assertTrue(prompt.startswith("You are Boss. Be brief."))
        self.assertIn("Specialists: hand them a subtask with delegate", prompt)
        self.assertIn("- helper: Uses alpha.", prompt)

    async def test_load_skill_with_a_persona_name_points_to_delegate(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([
            [get_function_tool_call("load_skill", json.dumps({"name": "helper"}), call_id="l1")],
            [get_text_message("ok")],
        ])
        assistant = self.build(model)
        events = [e async for e in Runtime(assistant.agent).run("x")]
        result = [e for e in events if isinstance(e, ToolCallResult)][0]
        self.assertEqual(result.error, "invalid_args")
        self.assertIn("use delegate with persona 'helper'", result.content)

    async def test_delegation_runs_the_specialist_with_its_skills(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([
            [get_function_tool_call("delegate", json.dumps({"persona": "helper", "task": "use alpha on x"}), call_id="d1")],
            [get_function_tool_call("use_alpha", json.dumps({"thing": "x"}), call_id="a1")],  # helper's turn 1
            [get_text_message("alpha says alpha-value: x")],  # helper's answer
            [get_text_message("Done: alpha-value: x")],  # main agent's answer
        ])
        assistant = self.build(model)
        events = [e async for e in Runtime(assistant.agent, prepare=assistant.prepare).run("please use the helper")]

        nested = [e for e in events if isinstance(e, SubagentEvent)]
        self.assertIn("use_alpha", [e.event.name for e in nested if hasattr(e.event, "name")])
        delegated = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"][0]
        self.assertEqual(delegated.content, "alpha says alpha-value: x")
        self.assertEqual(delegated.details["props"]["persona"], "helper")

    async def test_specialist_turn_limit(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([
            [get_function_tool_call("delegate", json.dumps({"persona": "helper", "task": "loop"}), call_id="d1")],
            [get_function_tool_call("use_alpha", json.dumps({"thing": "1"}), call_id="a1")],
            [get_function_tool_call("use_alpha", json.dumps({"thing": "2"}), call_id="a2")],
            [get_text_message("The helper ran out of steps.")],
        ])
        assistant = self.build(model)
        events = [e async for e in Runtime(assistant.agent).run("go")]
        delegated = [e for e in events if isinstance(e, ToolCallResult) and e.name == "delegate"][0]
        self.assertEqual(delegated.content, "Error: helper did not finish within 2 steps.")

    async def test_switch_preloads_persona_skills_and_changes_targets(self):
        assistant = self.build(FakeModel())
        with self.assertRaises(KeyError):
            assistant.switch("nobody")
        helper = assistant.switch("helper")
        self.assertEqual(helper.persona.name, "helper")
        self.assertNotIn("delegate", names(helper.core_tools))  # no other delegable persona left
        state: dict = {}
        events = helper.prepare("hello", state)
        self.assertEqual(events, [Custom("skill_loaded", {"skill": "alpha", "by": "persona"})])
        quiet = assistant.switch("quiet")
        delegate = [t for t in quiet.core_tools if t.name == "delegate"][0]
        self.assertEqual(delegate.params_json_schema["properties"]["persona"]["enum"], ["helper"])

    def test_unknown_default_persona_falls_back(self):
        assistant = self.build(FakeModel(), persona="missing")
        self.assertEqual(assistant.persona.name, "assistant")


if __name__ == "__main__":
    unittest.main()
