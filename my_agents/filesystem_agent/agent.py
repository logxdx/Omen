from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.filesystem_tools import FILESYSTEM_TOOLS
from tools.misc_tools import get_current_datetime
from .prompt import (
    FILESYSTEM_AGENT_SYSTEM_PROMPT,
    FILESYSTEM_AGENT_HANDOFF_INSTRUCTIONS,
)


config = AGENT_CONFIGS["filesystem_agent"]
instructions: str = FILESYSTEM_AGENT_SYSTEM_PROMPT
FILESYSTEM_TOOLS += [get_current_datetime]

filesystem_agent = my_agent(
    agent_name="Filesystem Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=FILESYSTEM_AGENT_HANDOFF_INSTRUCTIONS,
    tools=FILESYSTEM_TOOLS,
)
