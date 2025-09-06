import os
import datetime
from dotenv import load_dotenv
from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel

from tools.tools import (
    searx_search,
    search_youtube_videos,
    open_url_in_browser,
    get_weather_info,
    scrape_url,
)

load_dotenv()

BASE_URL = os.getenv("CEREBRAS_BASE_URL")
API_KEY = os.getenv("CEREBRAS_API_KEY")
MODEL_NAME = "openai/gpt-oss-120b"

litellm_model = LitellmModel(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL)


WEB_SEARCH_AGENT_PROMPT = f"""
You are a web search specialist agent. Your capabilities include:

CORE FUNCTIONS:
1. Perform web searches
2. Search for YouTube videos
3. Scrape webpage content from URLs
4. Open URLs in browser
5. Get weather information
6. Provide summaries and insights from web sources
7. Find specific information requested by users

SEARCH GUIDELINES:
- Always provide clear, accurate search results
- Include source URLs when available
- Summarize findings concisely
- If search fails, explain why and suggest alternatives
- Focus on recent, reliable sources when possible
- Use appropriate search engine based on the query type

RESPONSE FORMAT:
- Start with a brief summary of what you found
- Include relevant details and sources
- End with actionable insights or recommendations

LIMITATIONS:
- Cannot access paid or subscription content
- Cannot perform actions on websites (only read and search)

When users ask for web searches, information lookup, research tasks, or online content, use your search capabilities to provide comprehensive, accurate responses.

## Handoff back to the triage agent when the request requires it.

Current Date and Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""


def create_web_search_agent():
    return Agent(
        name="web_search_agent",
        instructions=WEB_SEARCH_AGENT_PROMPT,
        model=litellm_model,
        tools=[
            searx_search,
            scrape_url,
            search_youtube_videos,
            open_url_in_browser,
            get_weather_info,
        ],
    )
