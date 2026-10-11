import json
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from omen.agui import AgUiMapper
    from omen.server import create_app

    HAVE_SERVER_DEPS = True
except ImportError:  # fastapi / ag-ui-protocol not installed yet (uv sync)
    HAVE_SERVER_DEPS = False

from omen.assistant import build_assistant
from omen.core import events as om
from omen.ui.extract import Extractor
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message
from tests.test_skills import make_skill


def sse_events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


@unittest.skipUnless(HAVE_SERVER_DEPS, "fastapi / ag-ui-protocol not installed")
class AgUiMapperTests(unittest.TestCase):
    def test_lifecycle_text_reasoning_and_steps(self):
        m = AgUiMapper("t1", "r1")
        events = []
        for e in [
            om.RunStarted("x"), om.StepStarted(1), om.ReasoningContent("m1", "hmm"),
            om.TextMessageStart("m1"), om.TextMessageContent("m1", "Hi"), om.TextMessageEnd("m1", "Hi"),
            om.RunFinished("x", "done"),
        ]:
            events += [ev.type.value for ev in m.map(e)]
        self.assertEqual(events, [
            "RUN_STARTED", "STEP_STARTED", "REASONING_START", "REASONING_MESSAGE_START", "REASONING_MESSAGE_CONTENT",
            "REASONING_MESSAGE_END", "REASONING_END", "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END",
            "STEP_FINISHED", "RUN_FINISHED",
        ])

    def test_tool_result_ui_and_subagents(self):
        m = AgUiMapper("t1", "r1")
        ui = {"type": "delegation", "version": 1, "valid": True, "props": {"persona": "writer"}, "text": "draft"}
        out = []
        for e in [
            om.ToolCallStart("d1", "delegate"),
            om.SubagentEvent("d1", "writer", om.TextMessageStart("s1")),
            om.SubagentEvent("d1", "writer", om.TextMessageContent("s1", "draft")),
            om.ToolCallResult("d1", "delegate", "draft", ui, None),
            om.UserQuestion("q1", "Sure?", ["yes", "no"]),
        ]:
            out += m.map(e)
        types = [e.type.value for e in out]
        self.assertEqual(types, [
            "TOOL_CALL_START", "SUBAGENT_STARTED", "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT",
            "SUBAGENT_FINISHED", "TOOL_CALL_RESULT", "ACTIVITY_SNAPSHOT", "ACTIVITY_SNAPSHOT",
        ])
        self.assertEqual(out[2].subagent_run_id, "sub-d1")
        self.assertEqual((out[6].activity_type, out[6].content["tool_call_id"]), ("delegation", "d1"))
        self.assertEqual((out[7].activity_type, out[7].content["options"]), ("question", ["yes", "no"]))


@unittest.skipUnless(HAVE_SERVER_DEPS, "fastapi / ag-ui-protocol not installed")
class ServerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        make_skill(root / "skills", "alpha", ["alpha"], tool_name="use_alpha")
        self.model = FakeModel()

        def factory(persona=None):
            return build_assistant(
                persona=persona, model=self.model, skills_dirs=[root / "skills"],
                personas_dirs=[], memory_path=root / "m.jsonl",
            )

        async def no_llm(messages, schema):
            return "{}"

        app = create_app(sessions_dir=root / "sessions", assistant_factory=factory, extractor=Extractor(complete=no_llm))
        self.client = TestClient(app)

    def tearDown(self):
        self.dir.cleanup()

    def run_agent(self, text: str, **props) -> list[dict]:
        body = {
            "threadId": "thread-1", "runId": "run-1", "state": {}, "tools": [], "context": [],
            "forwardedProps": {"omen": props} if props else {},
            "messages": [{"id": "u1", "role": "user", "content": text}],
        }
        response = self.client.post("/agent", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        return sse_events(response.text)

    def test_agent_streams_ag_ui_events_with_components(self):
        self.model.add_multiple_turn_outputs([
            [get_function_tool_call("load_skill", json.dumps({"name": "alpha"}), call_id="l1")],
            [get_function_tool_call("use_alpha", json.dumps({"thing": "x"}), call_id="a1")],
            [get_text_message("| A | B |\n|---|---|\n| 1 | 2 |")],
        ])
        events = self.run_agent("use alpha")
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "RUN_STARTED")
        self.assertEqual(types[-1], "RUN_FINISHED")
        self.assertEqual(events[0]["threadId"], "thread-1")
        self.assertIn("TOOL_CALL_RESULT", types)
        activities = [e for e in events if e["type"] == "ACTIVITY_SNAPSHOT"]
        kinds = [a["activityType"] for a in activities]
        self.assertIn("alpha", kinds)  # use_alpha's details
        self.assertIn("table", kinds)  # extracted from the reply
        table = [a for a in activities if a["activityType"] == "table"][0]
        self.assertEqual(table["content"]["props"]["rows"], [["1", "2"]])

        history = self.client.get("/threads/thread-1").json()["messages"]
        tool = [m for m in history if m["role"] == "tool" and m["name"] == "use_alpha"][0]
        self.assertEqual(tool["ui"]["type"], "alpha")
        self.assertIn("thread-1", [t["id"] for t in self.client.get("/threads").json()])

    def test_capabilities_limit_components(self):
        self.model.add_multiple_turn_outputs([[get_text_message("| A | B |\n|---|---|\n| 1 | 2 |")]])
        events = self.run_agent("table please", components=["weather"])
        self.assertFalse([e for e in events if e["type"] == "ACTIVITY_SNAPSHOT"])

    def test_side_endpoints_and_schema(self):
        self.assertEqual(self.client.post("/threads/nope/abort").status_code, 404)
        self.model.add_multiple_turn_outputs([[get_text_message("hi")]])
        self.run_agent("hello")
        self.assertEqual(self.client.post("/threads/thread-1/answer", json={"text": "yes"}).status_code, 409)
        self.assertEqual(self.client.post("/threads/thread-1/messages", json={"text": "more"}).status_code, 409)
        self.assertEqual(self.client.post("/threads/thread-1/abort").json(), {"aborted": True})
        schema = self.client.get("/ui/schema").json()
        self.assertIn("weather", schema["components"])
        self.assertEqual(self.client.get("/health").json(), {"ok": True})
        bad = self.client.post("/agent", json={"threadId": "../x", "runId": "r", "state": {}, "tools": [],
                                               "context": [], "forwardedProps": {}, "messages": []})
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
