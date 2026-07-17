from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS

from tools.filesystem_tools import list_files, read_file, grep_file_content
from tools.search_tools import duckduckgo_web_search
from tools.web_tools import get_weather_info, open_url_in_browser
from config.agent_personality import get_personality
from .prompt import TRIAGE_AGENT_SYSTEM_PROMPT, TRIAGE_HANDOFF_INSTRUCTIONS

config = AGENT_CONFIGS["triage_agent"]
name, personality = get_personality()
instructions: str = personality + "\n\n" + TRIAGE_AGENT_SYSTEM_PROMPT
TOOLS = [
    list_files,
    read_file,
    grep_file_content,
    duckduckgo_web_search,
    get_weather_info,
    open_url_in_browser,
]

triage_agent = my_agent(
    agent_name=name.capitalize() + " (Triage)",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=TRIAGE_HANDOFF_INSTRUCTIONS,
    tools=TOOLS,
)
