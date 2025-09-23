from config.agent_config import AGENT_CONFIGS
from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel

from tools.search_tools import searx_search, search_youtube_videos
from tools.web_tools import open_url_in_browser, get_weather_info, scrape_url, download_audio, download_video
from tools.misc_tools import get_current_datetime
from .prompt import WEB_SEARCH_AGENT_PROMPT

config = AGENT_CONFIGS["web_search_agent"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME = config["MODEL_NAME"]

litellm_model = LitellmModel(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL)


def create_web_search_agent(handoffs=None):
    if handoffs is None:
        handoffs = []
    return Agent(
        name="Web Search Agent",
        instructions=WEB_SEARCH_AGENT_PROMPT,
        model=litellm_model,
        handoffs=handoffs,
        tools=[
            searx_search,
            scrape_url,
            search_youtube_videos,
            download_video,
            download_audio,
            open_url_in_browser,
            get_weather_info,
            get_current_datetime,
        ],
    )
