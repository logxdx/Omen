import asyncio
import json
import unittest

from agents.tool_context import ToolContext

from omen.core.tools import ToolResult, classify_error, extract_custom_data, tool, truncate


@tool
def get_weather(city: str, units: str = "celsius") -> ToolResult:
    """Current weather for a city.

    Args:
        city: City name, e.g. "Paris".
        units: "celsius" or "fahrenheit".
    """
    return ToolResult(f"{city}: 18 {units}", details={"type": "weather", "city": city})


@tool
def lookup(name: str) -> dict:
    """Find a contact."""
    return {"name": name, "email": f"{name.lower()}@example.com"}


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
def big() -> str:
    """Returns a lot."""
    return "line\n" * 100


def ctx(name: str, args: str) -> ToolContext:
    return ToolContext(context=None, tool_name=name, tool_call_id="c1", tool_arguments=args)


async def call(t, args: dict | str):
    raw = args if isinstance(args, str) else json.dumps(args)
    return await t.on_invoke_tool(ctx(t.name, raw), raw)


class SchemaTests(unittest.TestCase):
    def test_defaults_stay_optional(self):
        schema = get_weather.params_json_schema
        self.assertEqual(schema["required"], ["city"])
        self.assertEqual(set(schema["properties"]), {"city", "units"})
        self.assertFalse(get_weather.strict_json_schema)

    def test_description_from_docstring(self):
        self.assertEqual(get_weather.description, "Current weather for a city.")
        self.assertIn("Paris", get_weather.params_json_schema["properties"]["city"]["description"])


class InvokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_result_keeps_details(self):
        out = await call(get_weather, {"city": "Oslo"})
        self.assertIsInstance(out, ToolResult)
        self.assertEqual(str(out), "Oslo: 18 celsius")
        self.assertEqual(out.details, {"type": "weather", "city": "Oslo"})

    async def test_plain_returns_become_text(self):
        out = await call(lookup, {"name": "Tom"})
        self.assertEqual(json.loads(str(out)), {"name": "Tom", "email": "tom@example.com"})
        self.assertEqual(str(await call(slow_echo, {"text": "hi"})), "hi")

    async def test_exception_becomes_error_result(self):
        out = await call(broken, {})
        self.assertEqual(out.error, "exception")
        self.assertIn("disk on fire", str(out))

    async def test_invalid_arguments_are_reported_to_the_model(self):
        out = await call(get_weather, {"town": "Paris"})
        self.assertIsInstance(out, str)
        self.assertTrue(out.startswith("Error: invalid arguments for get_weather"))
        self.assertEqual(classify_error(out), "invalid_args")

    async def test_content_is_capped(self):
        out = await call(big, {})
        self.assertLess(len(str(out)), 120)
        self.assertIn("[truncated: showing", str(out))


class CustomDataTests(unittest.TestCase):
    def test_extracts_details_and_error(self):
        class Data:
            output = ToolResult("x", details={"type": "card"}, error="exception")

        self.assertEqual(extract_custom_data(Data()), {"ui": {"type": "card"}, "error": "exception"})

    def test_ignores_plain_outputs(self):
        class Data:
            output = "plain"

        self.assertIsNone(extract_custom_data(Data()))


class HelpersTests(unittest.TestCase):
    def test_classify_error(self):
        self.assertEqual(classify_error("Tool 'fly' not found."), "unknown_tool")
        self.assertEqual(classify_error("Error in x: boom"), "exception")
        self.assertIsNone(classify_error("Paris: 18C"))

    def test_truncate(self):
        self.assertEqual(truncate("abc", 10), "abc")
        out = truncate("a" * 90 + "\n" + "b" * 50, 100)
        self.assertTrue(out.startswith("a" * 90 + "\n[truncated: showing 90 of 141"))


if __name__ == "__main__":
    unittest.main()
