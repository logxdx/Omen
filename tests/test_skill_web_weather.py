import json
import sys
import types
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from agents.tool_context import ToolContext

from omen.config import REPO_ROOT
from omen.core.skills import Skills



def load(skill: str):
    """Discover skills now (each discovery re-imports skill modules) and return (tools, tools module)."""
    skills = Skills([REPO_ROOT / "skills"])
    return {t.name: t for t in skills.skills[skill].tools}, sys.modules[f"omen_skills.{skill}.tools"]

ARTICLE = """canonical: https://example.org/cones
meta-og:title: Cones
title: Cones - Example

# Cones

- [Español](https://es.example.org/cono "Spanish")
- [Français](https://fr.example.org/cone "French")

A [conifer cone](https://example.org/cone_(botany)) is a seed-bearing organ.

## Pollination

Pine cones are pollinated by wind. Pollen grains drift between trees in spring.

## Uses

Cones are used as fire starters and decorations.
"""


async def invoke(t, **args):
    raw = json.dumps(args)
    return await t.on_invoke_tool(ToolContext(context=None, tool_name=t.name, tool_call_id="c", tool_arguments=raw), raw)


class PageTests(unittest.TestCase):
    def setUp(self):
        global page
        load("web")
        page = sys.modules["omen_skills.web.page"]

    def test_clean_markdown(self):
        text = page.clean_markdown(ARTICLE)
        self.assertTrue(text.startswith("# Cones"))
        self.assertNotIn("Español", text)
        self.assertNotIn("https://", text)
        self.assertIn("A conifer cone is a seed-bearing organ.", text)

    def test_rank_returns_relevant_paragraphs_in_page_order(self):
        text = page.clean_markdown(ARTICLE)
        shown = page.rank(text, "how are pine cones pollinated", 200)
        self.assertIn("pollinated by wind", shown)
        self.assertNotIn("fire starters", shown)

    def test_fit(self):
        self.assertEqual(page.fit("short", 10), "short")
        self.assertLessEqual(len(page.fit("One sentence. " * 50, 100)), 100)


def fake_crawlberg(result=None, error=None):
    module = types.ModuleType("crawlberg")

    async def scrape(engine, url):
        if error:
            raise error
        return result

    module.scrape = scrape
    return module


def scrape_result(status=200, html="<html><body><p>ok</p></body></html>", text=ARTICLE, title="Cones - Example"):
    return NS(
        status_code=status, html=html, final_url="https://example.org/cones", js_render_hint=False,
        markdown=NS(content=text, fit_content=text), metadata=NS(title=title, description="About cones"),
        response_meta=NS(retry_after=None),
    )


class ReadUrlTests(unittest.IsolatedAsyncioTestCase):
    async def read(self, crawl, **args):
        tools, module = load("web")
        with mock.patch.dict(sys.modules, {"crawlberg": crawl}), mock.patch.object(module, "_crawl_engine", lambda: None):
            return await invoke(tools["read_url"], **args)

    async def test_ok_page_with_query(self):
        out = await self.read(fake_crawlberg(scrape_result()), url="example.org/cones", query="pollination")
        text = str(out)
        self.assertTrue(text.startswith("Cones - Example | https://example.org/cones | showing"))
        self.assertIn("pollinated by wind", text)
        self.assertEqual(out.details["type"], "link_preview")
        self.assertIsNone(out.error)

    async def test_challenge_page_is_reported_as_blocked(self):
        html = '<html><script src="/cdn-cgi/challenge-platform/h/b"></script>Just a moment...</html>'
        out = await self.read(fake_crawlberg(scrape_result(html=html, text="")), url="https://x.org")
        self.assertTrue(str(out).startswith("BLOCKED (cloudflare)"))
        self.assertEqual(out.error, "unavailable")

    async def test_not_found_and_errors(self):
        out = await self.read(fake_crawlberg(scrape_result(status=404)), url="https://x.org/missing")
        self.assertTrue(str(out).startswith("NOT_FOUND"))
        out = await self.read(fake_crawlberg(error=RuntimeError("timeout: took too long")), url="https://slow.org")
        self.assertTrue(str(out).startswith("TIMEOUT"))


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_formats_results(self):
        results = [NS(title="Pine cone", link="https://a.org", snippet="About cones", to_dict=lambda: {"title": "Pine cone"})]
        tools, module = load("web")
        with mock.patch.object(module, "ddg_search", lambda q, max_results: results):
            out = await invoke(tools["search"], query="pine cones")
        self.assertEqual(str(out), "1. Pine cone\n   https://a.org\n   About cones")
        self.assertEqual(out.details["type"], "search_results")


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_card(self):
        data = {
            "current_condition": [{
                "temp_C": "18", "FeelsLikeC": "17", "humidity": "70", "windspeedKmph": "12",
                "weatherDesc": [{"value": "Light rain "}], "localObsDateTime": "2026-10-11 09:00 AM",
            }],
            "nearest_area": [{"areaName": [{"value": "Paris"}], "country": [{"value": "France"}]}],
            "weather": [{"date": "2026-10-11", "mintempC": "12", "maxtempC": "19"}],
        }
        tools, module = load("weather")
        with mock.patch.object(module, "fetch_weather_json", lambda city: data):
            out = await invoke(tools["get_weather"], city="Paris")
        self.assertTrue(str(out).startswith("Paris, France: 18°C (feels like 17°C), Light rain"))
        self.assertEqual(out.details["temp_c"], 18)
        self.assertEqual(out.details["forecast"], [{"date": "2026-10-11", "min_c": 12, "max_c": 19}])


if __name__ == "__main__":
    unittest.main()
