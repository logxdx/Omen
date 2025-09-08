from my_agents.agent_config import AGENT_CONFIGS
from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel

from tools.tools import (
    searx_search,
    search_youtube_videos,
    open_url_in_browser,
    get_weather_info,
    scrape_url,
    get_current_datetime,
)

config = AGENT_CONFIGS["web_search_agent"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME = config["MODEL_NAME"]

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

## Handoff Options
You can handoff to other agents for collaborative tasks:
- **ideation_agent**: For brainstorming ideas based on search results, creative analysis, or theoretical discussions
- **filesystem_agent**: For saving search results to files, organizing research data, or managing local documents
- **triage_agent**: For routing complex requests or when unsure which agent to involve next
"""


def create_web_search_agent(handoffs=None):
    if handoffs is None:
        handoffs = []
    return Agent(
        name="web_search_agent",
        instructions=WEB_SEARCH_AGENT_PROMPT,
        model=litellm_model,
        handoffs=handoffs,
        tools=[
            searx_search,
            scrape_url,
            search_youtube_videos,
            open_url_in_browser,
            get_weather_info,
            get_current_datetime,
        ],
    )
