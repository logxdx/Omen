import asyncio
import json
import unittest

from omen.core.tools import ToolContext, ToolRegistry, ToolResult, parse_arguments, tool, truncate


@tool
def get_weather(city: str, units: str = "celsius") -> str:
    """Current weather for a city.

    Args:
        city: City name, e.g. "Paris".
        units: "celsius" or
            "fahrenheit".
    """
    return f"{city}: 18 {units}"


@tool
def note(text: str, tag: str | None = None, ctx: ToolContext = None) -> dict:
    """Save a note."""
    ctx.state["saved"] = text
    return {"saved": text, "tag": tag}


@tool
async def slow_echo(text: str) -> str:
    """Echo text asynchronously."""
    await asyncio.sleep(0)
    return text


@tool
def broken() -> str:
    """Always fails."""
    raise RuntimeError("disk on fire")


@tool(max_chars=50)
def big() -> ToolResult:
    """Returns a lot."""
    return ToolResult("line\n" * 100, details={"type": "table"})


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


class SchemaTests(unittest.TestCase):
    def test_schema_from_signature_and_docstring(self):
        fn = get_weather.schema()["function"]
        self.assertEqual(fn["name"], "get_weather")
        self.assertEqual(fn["description"], "Current weather for a city.")
        params = fn["parameters"]
        self.assertEqual(params["required"], ["city"])
        self.assertEqual(params["properties"]["units"]["default"], "celsius")
        self.assertEqual(params["properties"]["units"]["description"], '"celsius" or "fahrenheit".')
        self.assertNotIn("title", list(walk_keys(params)))

    def test_optional_collapses_and_ctx_is_hidden(self):
        params = note.schema()["function"]["parameters"]
        self.assertEqual(set(params["properties"]), {"text", "tag"})
        self.assertEqual(params["properties"]["tag"]["type"], "string")
        self.assertNotIn("anyOf", params["properties"]["tag"])

    def test_signature_summary(self):
        self.assertEqual(get_weather.signature(), "city (string), units (string, optional)")


class ParseArgumentsTests(unittest.TestCase):
    def test_repairs(self):
        cases = {
            '{"a": 1}': {"a": 1},
            '```json\n{"a": 1}\n```': {"a": 1},
            '{"a": 1,}': {"a": 1},
            'Sure! {"a": 1}': {"a": 1},
            json.dumps('{"a": 1}'): {"a": 1},  # double-encoded
            "": {},
        }
        for raw, expected in cases.items():
            self.assertEqual(parse_arguments(raw), expected, raw)

    def test_rejects_non_objects(self):
        for raw in ("[1, 2]", "not json"):
            with self.assertRaises(ValueError):
                parse_arguments(raw)


class ExecuteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reg = ToolRegistry([get_weather, note, slow_echo, broken, big])

    async def test_success(self):
        name, r = await self.reg.execute("get_weather", '{"city": "Paris"}')
        self.assertEqual((name, r.content, r.error), ("get_weather", "Paris: 18 celsius", None))

    async def test_fuzzy_names(self):
        for requested in ("functions.get_weather", "getWeather", "GetWeather", "get-weather", "get_wether"):
            name, r = await self.reg.execute(requested, '{"city": "Oslo"}')
            self.assertEqual(name, "get_weather", requested)
            self.assertFalse(r.is_error, requested)

    async def test_unknown_tool_lists_available(self):
        _, r = await self.reg.execute("fly_to_moon", "{}")
        self.assertEqual(r.error, "unknown_tool")
        self.assertIn("get_weather", r.content)

    async def test_hidden_tools_are_not_callable(self):
        self.reg.hide("get_weather")
        _, r = await self.reg.execute("get_weather", '{"city": "Oslo"}')
        self.assertEqual(r.error, "unknown_tool")
        self.reg.show("get_weather")
        _, r = await self.reg.execute("get_weather", '{"city": "Oslo"}')
        self.assertIsNone(r.error)

    async def test_validation_error_is_actionable(self):
        _, r = await self.reg.execute("get_weather", '{"town": "Paris"}')
        self.assertEqual(r.error, "invalid_args")
        self.assertIn("city", r.content)
        self.assertIn("Expected: city (string), units (string, optional)", r.content)

    async def test_bad_json(self):
        _, r = await self.reg.execute("get_weather", "{city: Paris")
        self.assertEqual(r.error, "invalid_args")

    async def test_wrapped_arguments_are_unwrapped(self):
        _, r = await self.reg.execute("get_weather", '{"arguments": {"city": "Rome"}}')
        self.assertEqual(r.content, "Rome: 18 celsius")

    async def test_context_injection_and_dict_result(self):
        ctx = ToolContext(registry=self.reg)
        _, r = await self.reg.execute("note", {"text": "milk"}, ctx)
        self.assertEqual(ctx.state["saved"], "milk")
        self.assertEqual(json.loads(r.content), {"saved": "milk", "tag": None})

    async def test_async_tool(self):
        _, r = await self.reg.execute("slow_echo", '{"text": "hi"}')
        self.assertEqual(r.content, "hi")

    async def test_exception_becomes_error_result(self):
        _, r = await self.reg.execute("broken", "{}")
        self.assertEqual(r.error, "exception")
        self.assertIn("disk on fire", r.content)

    async def test_content_is_capped_details_kept(self):
        _, r = await self.reg.execute("big", "{}")
        self.assertLess(len(r.content), 120)
        self.assertIn("[truncated: showing", r.content)
        self.assertEqual(r.details, {"type": "table"})


class TruncateTests(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(truncate("abc", 10), "abc")

    def test_cuts_at_newline_near_limit(self):
        text = "a" * 90 + "\n" + "b" * 50
        out = truncate(text, 100)
        self.assertTrue(out.startswith("a" * 90 + "\n[truncated: showing 90 of 141"))


if __name__ == "__main__":
    unittest.main()
