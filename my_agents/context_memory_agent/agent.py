from my_agents.base_agent import my_agent, agent_config
from config.agent_config import AGENT_CONFIGS
from tools.context_manager_tools import CONTEXT_TOOLS
from tools.misc_tools import get_current_datetime
from .prompt import (
    CONTEXT_MANAGER_AGENT_SYSTEM_PROMPT,
    CONTEXT_MEMORY_HANDOFF_INSTRUCTIONS,
)

config = AGENT_CONFIGS["context_manager_agent"]
instructions: str = CONTEXT_MANAGER_AGENT_SYSTEM_PROMPT
CONTEXT_TOOLS += [get_current_datetime]

context_agent = my_agent(
    agent_name="Context Manager Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=CONTEXT_MEMORY_HANDOFF_INSTRUCTIONS,
    tools=CONTEXT_TOOLS,
)
