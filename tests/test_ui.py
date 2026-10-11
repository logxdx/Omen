import json
import unittest

from agents import Agent

from omen.core import Runtime, ToolResult, tool
from omen.core.events import TextMessageContent, ToolCallResult, UIComponent
from omen.ui.components import TYPES, json_schema, payload
from omen.ui.extract import Extractor, choices_from_text, components_for, strip_hints, table_from_markdown
from tests.sdk_fake_model import FakeModel
from tests.sdk_responses import get_function_tool_call, get_text_message

REPLY_WITH_TABLE = """Here are the prices:

| Item | Price |
|------|------:|
| Eggs | 3.50 |
| **Bread** | `2.20` |

Anything else?"""


class PayloadTests(unittest.TestCase):
    def test_valid_component(self):
        p = payload({"type": "weather", "place": "Pune", "temp_c": 26, "condition": "Cloudy", "extra": 1}, "Pune 26C")
        self.assertTrue(p.valid)
        self.assertEqual(p.props, {"place": "Pune", "temp_c": 26, "condition": "Cloudy", "forecast": []})
        self.assertEqual(p.text, "Pune 26C")

    def test_invalid_and_unknown_still_deliver_text(self):
        bad = payload({"type": "weather", "city": "Pune"}, "fallback")
        self.assertFalse(bad.valid)
        self.assertEqual((bad.props, bad.text), ({"city": "Pune"}, "fallback"))
        self.assertFalse(payload({"type": "mystery"}, "x").valid)
        self.assertIsNone(payload(None, "x"))
        self.assertIsNone(payload({"no": "type"}, "x"))

    def test_schema_covers_every_component(self):
        schema = json_schema()
        self.assertEqual(set(schema["components"]), set(TYPES))
        self.assertIn("weather", TYPES)


class RuleTests(unittest.TestCase):
    def test_table(self):
        table = table_from_markdown(REPLY_WITH_TABLE)
        self.assertEqual(table.title, "Here are the prices")
        self.assertEqual(table.columns, ["Item", "Price"])
        self.assertEqual(table.rows, [["Eggs", "3.50"], ["Bread", "2.20"]])
        self.assertIsNone(table_from_markdown("no table | here"))

    def test_choices(self):
        choice = choices_from_text("I found two flights.\nWhich one do you want?\n1. 9:00 to Delhi\n2. 13:30 to Delhi")
        self.assertEqual(choice.question, "Which one do you want?")
        self.assertEqual(choice.options, ["9:00 to Delhi", "13:30 to Delhi"])
        self.assertIsNone(choices_from_text("Steps:\n1. a"))
        self.assertIsNone(choices_from_text("Here is a list\n- a\n- b"))  # no question

    def test_strip_hints(self):
        self.assertEqual(strip_hints("Sales grew.\n<ui:chart>\n<ui:CHART>"), ("Sales grew.", ["chart"]))


def fake_complete(*replies):
    calls = []

    async def complete(messages, schema):
        calls.append({"messages": messages, "schema": schema})
        return replies[len(calls) - 1]

    return complete, calls


class ExtractorTests(unittest.IsolatedAsyncioTestCase):
    async def test_fills_component_from_json(self):
        complete, calls = fake_complete('{"title": "Sales", "kind": "line", "labels": ["Q1", "Q2"], "values": [3, 5]}')
        p = await Extractor(complete=complete).extract("chart", "Sales were 3 in Q1 and 5 in Q2.")
        self.assertEqual((p.type, p.valid), ("chart", True))
        self.assertEqual(p.props["values"], [3.0, 5.0])
        self.assertNotIn("type", calls[0]["schema"]["schema"]["properties"])

    async def test_retries_once_with_the_error(self):
        complete, calls = fake_complete('{"title": 1}', '<think>ok</think>```json\n{"title": "Pune", "body": "Hot."}\n```')
        p = await Extractor(complete=complete).extract("card", "Pune is hot.")
        self.assertEqual(p.props, {"title": "Pune", "body": "Hot."})
        self.assertEqual(len(calls), 2)
        self.assertIn("not valid", calls[1]["messages"][-1]["content"])

    async def test_invented_urls_are_dropped(self):
        complete, _ = fake_complete('{"title": "Pune", "body": "A city.", "url": "https://en.wikipedia.org/wiki/Pune"}')
        p = await Extractor(complete=complete).extract("card", "Pune is a city.")
        self.assertNotIn("url", p.props)
        complete, _ = fake_complete('{"title": "Docs", "body": "Read them.", "url": "https://docs.example.org"}')
        p = await Extractor(complete=complete).extract("card", "See https://docs.example.org for docs.")
        self.assertEqual(p.props["url"], "https://docs.example.org")

    async def test_model_errors_mean_no_component(self):
        async def down(messages, schema):
            raise ConnectionError("Loading model")

        self.assertIsNone(await Extractor(complete=down).extract("chart", "x"))

    async def test_gives_up_after_two_failures(self):
        complete, calls = fake_complete("nope", "still nope")
        self.assertIsNone(await Extractor(complete=complete).extract("card", "x"))
        self.assertEqual(len(calls), 2)

    async def test_components_for_combines_rules_and_hints(self):
        complete, calls = fake_complete('{"title": "Prices", "body": "Eggs 3.50, bread 2.20."}')
        found = await components_for(REPLY_WITH_TABLE + "\n<ui:card>", Extractor(complete=complete))
        self.assertEqual([p.type for p in found], ["table", "card"])
        only_tables = await components_for(REPLY_WITH_TABLE + "\n<ui:card>", Extractor(complete=complete), {"table"})
        self.assertEqual([p.type for p in only_tables], ["table"])


@tool
def get_weather(city: str) -> ToolResult:
    """Weather.

    Args:
        city: City.
    """
    return ToolResult(f"{city}: 26°C", details={"type": "weather", "place": city, "temp_c": 26, "condition": "Cloudy"})


class RuntimeUITests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_details_are_payloads_and_filtered_by_capability(self):
        def make():
            model = FakeModel()
            model.add_multiple_turn_outputs([
                [get_function_tool_call("get_weather", json.dumps({"city": "Pune"}), call_id="w1")],
                [get_text_message("26°C.")],
            ])
            return Agent(name="a", model=model, tools=[get_weather])

        events = [e async for e in Runtime(make()).run("weather?")]
        result = [e for e in events if isinstance(e, ToolCallResult)][0]
        self.assertEqual(result.details["type"], "weather")
        self.assertTrue(result.details["valid"])
        self.assertEqual(result.details["props"]["place"], "Pune")

        events = [e async for e in Runtime(make(), ui={"table"}).run("weather?")]
        self.assertIsNone([e for e in events if isinstance(e, ToolCallResult)][0].details)

    async def test_reply_components_and_hidden_hint_tags(self):
        model = FakeModel()
        model.add_multiple_turn_outputs([[get_text_message(REPLY_WITH_TABLE + "\n<ui:card>")]])
        complete, _ = fake_complete('{"title": "Prices", "body": "Eggs and bread."}')

        async def components(text, ui, request=""):
            return await components_for(text, Extractor(complete=complete), ui)

        rt = Runtime(Agent(name="a", model=model), components=components)
        events = [e async for e in rt.run("prices?")]
        visible = "".join(e.delta for e in events if isinstance(e, TextMessageContent))
        self.assertNotIn("<ui:", visible)
        self.assertIn("| Eggs | 3.50 |", visible)
        found = [e.payload["type"] for e in events if isinstance(e, UIComponent)]
        self.assertEqual(found, ["table", "card"])
        self.assertEqual(rt.state["ui_hints"], ["chart", "card"])


if __name__ == "__main__":
    unittest.main()


class StreamingMarkerTests(unittest.TestCase):
    def run_deltas(self, deltas):
        from types import SimpleNamespace as NS

        from omen.core.events import TextMessageEnd
        from omen.core.runtime import EventMapper

        mapper, out = EventMapper(), []
        for d in deltas:
            out += mapper.map(NS(type="raw_response_event", data=NS(type="response.output_text.delta", delta=d)))
        out += mapper.map(NS(type="raw_response_event", data=NS(type="response.output_item.done", item=NS(type="message"))))
        visible = "".join(e.delta for e in out if isinstance(e, TextMessageContent))
        return visible, [e for e in out if isinstance(e, TextMessageEnd)][0].text

    def test_marker_split_across_chunks_is_hidden(self):
        visible, full = self.run_deltas(["Sales rose. <u", "i:ch", "art>"])
        self.assertEqual(visible, "Sales rose. ")
        self.assertEqual(full, "Sales rose. <ui:chart>")

    def test_lookalike_tail_is_flushed(self):
        visible, _ = self.run_deltas(["a < b and x <", "u"])
        self.assertEqual(visible, "a < b and x <u")


class ChartRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_asking_for_a_chart_extracts_one_without_a_hint(self):
        complete, calls = fake_complete('{"title": "Spending", "kind": "bar", "labels": ["food", "rent"], "values": [1, 2]}')
        found = await components_for("Food is 1, rent is 2.", Extractor(complete=complete), {"chart"}, "Chart my spending: food 1, rent 2")
        self.assertEqual([p.type for p in found], ["chart"])
        self.assertIn("Chart my spending", calls[0]["messages"][1]["content"])  # the request is part of the context

    async def test_no_chart_without_a_request_or_numbers(self):
        complete, calls = fake_complete("{}")
        self.assertEqual(await components_for("Hello there.", Extractor(complete=complete), {"chart"}, "hi"), [])
        self.assertEqual(await components_for("Sure.", Extractor(complete=complete), {"chart"}, "draw a chart of my mood"), [])
        self.assertEqual(calls, [])
