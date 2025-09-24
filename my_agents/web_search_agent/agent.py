from base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.search_tools import searx_search, search_youtube_videos
from tools.web_tools import (
    open_url_in_browser,
    get_weather_info,
    scrape_url,
    download_audio,
    download_video,
)
from tools.misc_tools import get_current_datetime
from .prompt import WEB_SEARCH_AGENT_SYSTEM_PROMPT, WEB_SEARCH_HANDOFF_INSTRUCTIONS


config = AGENT_CONFIGS["web_search_agent"]
instructions: str = WEB_SEARCH_AGENT_SYSTEM_PROMPT

web_search_agent = my_agent(
    agent_name="Web Search Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=WEB_SEARCH_HANDOFF_INSTRUCTIONS,
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
