from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.search_tools import SEARCH_TOOLS
from tools.web_tools import WEB_TOOLS
from tools.misc_tools import get_current_datetime
from .prompt import WEB_SEARCH_AGENT_SYSTEM_PROMPT, WEB_SEARCH_HANDOFF_INSTRUCTIONS


config = AGENT_CONFIGS["web_search_agent"]
instructions: str = WEB_SEARCH_AGENT_SYSTEM_PROMPT
TOOLS = SEARCH_TOOLS + WEB_TOOLS + [get_current_datetime]

web_search_agent = my_agent(
    agent_name="Web Search Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=WEB_SEARCH_HANDOFF_INSTRUCTIONS,
    tools=TOOLS,
)
