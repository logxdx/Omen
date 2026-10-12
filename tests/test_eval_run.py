import json
import unittest

import yaml

from evals.run import HERE, run_task
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message

WEATHER_TURNS = {
    "id": "mt",
    "turns": [
        {"prompt": "Weather in Paris?", "expect_tools": ["get_weather"], "expect_answer": ["18"]},
        {
            "prompt": "And in Fahrenheit?",
            "expect_tools": ["get_weather"],
            "expect_args": {"get_weather": {"city": "paris", "units": "f"}},
            "expect_answer": ["64"],
        },
    ],
}


def weather_call(args: dict, call_id: str):
    return [get_function_tool_call("get_weather", json.dumps(args), call_id=call_id)]


class MultiTurnEvalTests(unittest.IsolatedAsyncioTestCase):
    async def test_turns_share_one_session_and_are_checked_separately(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([
            weather_call({"city": "Paris"}, "c1"),
            [get_text_message("It's 18°C in Paris.")],
            weather_call({"city": "Paris", "units": "fahrenheit"}, "c2"),
            [get_text_message("That's 64°F.")],
        ])
        result = await run_task(WEATHER_TURNS, model)

        self.assertEqual(result.failures, [])
        self.assertTrue(result.passed)
        self.assertEqual(result.answers, ["It's 18°C in Paris.", "That's 64°F."])
        self.assertEqual([c["turn"] for c in result.calls], [1, 2])
        self.assertEqual(result.steps, 4)
        seen = json.dumps(model.last_turn_args["input"], ensure_ascii=False)
        self.assertIn("Weather in Paris?", seen)  # turn 2 saw turn 1
        self.assertIn("18°C", seen)

    async def test_failures_name_their_turn(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([
            weather_call({"city": "Paris"}, "c1"),
            [get_text_message("It's 18°C in Paris.")],
            [get_text_message("Still 18°C.")],  # answered from memory, in the wrong unit
        ])
        result = await run_task(WEATHER_TURNS, model)

        self.assertFalse(result.passed)
        self.assertIn("turn 2: missing tool call: get_weather", result.failures)
        self.assertIn("turn 2: answer missing '64'", result.failures)
        self.assertFalse(any(f.startswith("turn 1") for f in result.failures))

    def test_task_file_is_well_formed(self):
        tasks = yaml.safe_load((HERE / "tasks.yaml").read_text())
        self.assertEqual(len({t["id"] for t in tasks}), len(tasks))
        for task in tasks:
            turns = task.get("turns") or [task]
            self.assertTrue(turns and all(t.get("prompt") for t in turns), task["id"])
            self.assertFalse("turns" in task and "prompt" in task, task["id"])


if __name__ == "__main__":
    unittest.main()
