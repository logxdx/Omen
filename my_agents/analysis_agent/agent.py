from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.misc_tools import MISC_TOOLS
from tools.web_tools import scrape_url, open_url_in_browser
from tools.search_tools import SEARCH_TOOLS
from tools.filesystem_tools import FILESYSTEM_TOOLS
from tools.data_tools import DATA_ANALYSIS_TOOLS
from tools.automation_tools import AUTOMATION_TOOLS
from .prompt import ANALYSIS_AGENT_SYSTEM_PROMPT, ANALYSIS_AGENT_HANDOFF_INSTRUCTIONS


config = AGENT_CONFIGS["analysis_agent"]
instructions: str = ANALYSIS_AGENT_SYSTEM_PROMPT

ANALYSIS_AGENT_TOOLS = (
    MISC_TOOLS
    + FILESYSTEM_TOOLS
    + DATA_ANALYSIS_TOOLS
    + AUTOMATION_TOOLS
    + [scrape_url, open_url_in_browser]
    + SEARCH_TOOLS
)

analysis_agent = my_agent(
    agent_name="Analysis Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=ANALYSIS_AGENT_HANDOFF_INSTRUCTIONS,
    tools=ANALYSIS_AGENT_TOOLS,
)
