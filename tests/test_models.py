import json
import unittest

from openai.types.responses import ResponseFunctionToolCall, ResponseReasoningItem
from openai.types.responses.response_reasoning_item import Summary

from omen.core.models import STUCK_REPLY, _message, is_degenerate, parse_text_tool_calls, repair_output

TOOLS = {"grep", "get_weather"}


def reasoning(text: str) -> ResponseReasoningItem:
    return ResponseReasoningItem(id="__fake_id__", type="reasoning", summary=[Summary(text=text, type="summary_text")])


def kinds(items):
    return [i.type for i in items]


class ParseTextToolCallsTests(unittest.TestCase):
    def test_glm_style(self):
        text = "Let me look.\n<tool_call>grep\n<arg_key>pattern</arg_key>\n<arg_value>wifi</arg_value>\n<arg_key>path</arg_key>\n<arg_value>notes</arg_value>\n</tool_call>"
        calls, remaining = parse_text_tool_calls(text, TOOLS)
        self.assertEqual([c.name for c in calls], ["grep"])
        self.assertEqual(json.loads(calls[0].arguments), {"pattern": "wifi", "path": "notes"})
        self.assertEqual(remaining, "Let me look.")

    def test_json_style_and_unclosed(self):
        calls, _ = parse_text_tool_calls('<tool_call>{"name": "get_weather", "arguments": {"city": "Pune"}}', TOOLS)
        self.assertEqual(json.loads(calls[0].arguments), {"city": "Pune"})

    def test_unknown_tool_is_left_as_text(self):
        text = "<tool_call>teleport<arg_key>to</arg_key><arg_value>mars</arg_value></tool_call>"
        self.assertEqual(parse_text_tool_calls(text, TOOLS), ([], text))


class RepairOutputTests(unittest.TestCase):
    def test_answer_only_in_reasoning_becomes_the_message(self):
        items = repair_output([reasoning("Your file says: trip to Goa.")], TOOLS)
        self.assertEqual(kinds(items), ["reasoning", "message"])
        self.assertEqual(items[-1].content[0].text, "Your file says: trip to Goa.")

    def test_text_tool_call_becomes_a_function_call(self):
        msg = _message("<tool_call>grep<arg_key>pattern</arg_key><arg_value>milk</arg_value></tool_call>")
        items = repair_output([msg], TOOLS)
        self.assertEqual(kinds(items), ["function_call"])
        self.assertEqual(items[0].name, "grep")

    def test_tool_call_inside_reasoning(self):
        items = repair_output([reasoning("<tool_call>get_weather<arg_key>city</arg_key><arg_value>Pune</arg_value>")], TOOLS)
        self.assertEqual(kinds(items), ["reasoning", "function_call"])

    def test_repetition_loops_are_never_shown(self):
        loop = 'it is likely a typo for "Crawford" - wait, actually I think they mean "Crawford" - ' * 40
        self.assertTrue(is_degenerate(loop))
        self.assertFalse(is_degenerate("A normal answer with varied words. " * 3))
        for items in ([reasoning(loop)], [_message(loop)]):
            repaired = repair_output(items, TOOLS)
            self.assertEqual(repaired[-1].content[0].text, STUCK_REPLY)

    def test_normal_outputs_are_untouched(self):
        call = ResponseFunctionToolCall(id="x", call_id="c", name="grep", arguments="{}", type="function_call")
        normal = [reasoning("thinking"), _message("Hello")]
        self.assertEqual(repair_output(list(normal), TOOLS), normal)
        self.assertEqual(repair_output([reasoning("plan"), call], TOOLS), [reasoning("plan"), call])


if __name__ == "__main__":
    unittest.main()


class EmptyRetryTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, responses):
        from types import SimpleNamespace as NS
        from unittest import mock

        from agents.extensions.models.litellm_model import LitellmModel

        from omen.core.models import OmenModel

        calls = []

        async def fake_stream(self, *args, **kwargs):
            output = responses[len(calls)]
            calls.append(1)
            yield NS(type="response.created")
            yield NS(type="response.completed", response=NS(output=list(output)))

        with mock.patch.object(LitellmModel, "stream_response", fake_stream):
            model = OmenModel(model="openai/x", base_url="http://x", api_key="k")
            events = [e async for e in model.stream_response(None, [], None, [], None, [], None)]
        return events, calls

    async def test_empty_response_is_retried_once(self):
        events, calls = await self.collect([[], [_message("Here you go.")]])
        self.assertEqual(len(calls), 2)
        completed = [e for e in events if e.type == "response.completed"]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].response.output[0].content[0].text, "Here you go.")

    async def test_normal_response_is_not_retried(self):
        events, calls = await self.collect([[_message("Hi")], [_message("never")]])
        self.assertEqual(len(calls), 1)

    def test_is_empty(self):
        from omen.core.models import is_empty

        self.assertTrue(is_empty([]))
        self.assertTrue(is_empty([reasoning("thinking"), _message("  ")]))
        self.assertFalse(is_empty([_message("hi")]))
