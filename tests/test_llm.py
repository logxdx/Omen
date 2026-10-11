import json
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from omen.config import ModelConfig
from omen.core.llm import Completion, LiteLLMClient, ReasoningDelta, TagRouter, TextDelta, assemble

TOOLS = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]


def chunk(content=None, tool_calls=None, reasoning=None, finish=None, usage=None):
    delta = NS(content=content, tool_calls=tool_calls, reasoning_content=reasoning)
    return NS(choices=[NS(delta=delta, finish_reason=finish)], usage=usage)


def tc(index, id=None, name=None, arguments=None):
    return NS(index=index, id=id, function=NS(name=name, arguments=arguments))


async def agen(items):
    for item in items:
        yield item


async def collect(chunks, tool_names=frozenset({"get_weather"})):
    return [item async for item in assemble(agen(chunks), set(tool_names))]


class TagRouterTests(unittest.TestCase):
    def run_router(self, chunks):
        router = TagRouter()
        out = []
        for c in chunks:
            out += router.feed(c)
        out += router.flush()
        merged = []
        for channel, text in out:
            if merged and merged[-1][0] == channel:
                merged[-1] = (channel, merged[-1][1] + text)
            else:
                merged.append((channel, text))
        return merged

    def test_tags_split_across_chunks(self):
        self.assertEqual(
            self.run_router(["Hel", "lo <th", "ink>secret</thi", "nk> world"]),
            [("text", "Hello "), ("reasoning", "secret"), ("text", " world")],
        )

    def test_non_tags_pass_through(self):
        self.assertEqual(self.run_router(["a <b> c <", "3"]), [("text", "a <b> c <3")])

    def test_unclosed_tag_flushes_into_its_channel(self):
        self.assertEqual(self.run_router(["<think>still going"]), [("reasoning", "still going")])


class AssembleTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_and_inline_reasoning(self):
        items = await collect([chunk("<think>hmm</think>"), chunk("Hi "), chunk("there", finish="stop")])
        self.assertEqual([i.text for i in items if isinstance(i, TextDelta)], ["Hi ", "there"])
        self.assertEqual([i.text for i in items if isinstance(i, ReasoningDelta)], ["hmm"])
        final = items[-1]
        self.assertIsInstance(final, Completion)
        self.assertEqual((final.text, final.reasoning, final.finish_reason), ("Hi there", "hmm", "stop"))

    async def test_reasoning_content_field(self):
        items = await collect([chunk(reasoning="step 1"), chunk("answer")])
        self.assertEqual(items[-1].reasoning, "step 1")

    async def test_native_tool_call_deltas_are_joined(self):
        items = await collect([
            chunk(tool_calls=[tc(0, id="call_a", name="get_weather", arguments='{"ci')]),
            chunk(tool_calls=[tc(0, arguments='ty": "Paris"}')]),
            chunk(finish="tool_calls", usage={"total_tokens": 42}),
        ])
        final = items[-1]
        self.assertEqual(len(final.tool_calls), 1)
        call = final.tool_calls[0]
        self.assertEqual((call.id, call.name, json.loads(call.arguments)), ("call_a", "get_weather", {"city": "Paris"}))
        self.assertEqual(final.usage, {"total_tokens": 42})

    async def test_text_tool_call_block_is_recovered_and_hidden(self):
        items = await collect([
            chunk("Let me check. <tool_"),
            chunk('call>{"name": "get_weather", "arguments": {"city": "Paris"}}</tool_call>'),
        ])
        self.assertEqual("".join(i.text for i in items if isinstance(i, TextDelta)), "Let me check. ")
        final = items[-1]
        self.assertEqual(final.text, "Let me check.")
        self.assertEqual(final.tool_calls[0].name, "get_weather")
        self.assertEqual(json.loads(final.tool_calls[0].arguments), {"city": "Paris"})

    async def test_bare_json_tool_call_only_for_known_tools(self):
        known = await collect([chunk('{"name": "get_weather", "parameters": {"city": "Oslo"}}')])
        self.assertEqual(known[-1].tool_calls[0].name, "get_weather")
        self.assertEqual(known[-1].text, "")
        unknown = await collect([chunk('{"name": "other", "arguments": {}}')])
        self.assertEqual(unknown[-1].tool_calls, [])


class LiteLLMClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_shape(self):
        captured = {}

        async def fake_acompletion(**kwargs):
            captured.update(kwargs)
            return agen([chunk("ok", finish="stop")])

        config = ModelConfig(model="openai/jarvis", base_url="http://x/v1", api_key="k",
                             extra_body={"think": False})
        with mock.patch("litellm.acompletion", fake_acompletion):
            items = [i async for i in LiteLLMClient(config).stream([{"role": "user", "content": "hi"}], TOOLS)]

        self.assertEqual(items[-1].text, "ok")
        self.assertEqual(captured["model"], "openai/jarvis")
        self.assertEqual(captured["api_base"], "http://x/v1")
        self.assertTrue(captured["stream"])
        self.assertEqual(captured["tools"], TOOLS)
        self.assertIs(captured["parallel_tool_calls"], False)
        self.assertEqual(captured["extra_body"], {"think": False})


if __name__ == "__main__":
    unittest.main()
