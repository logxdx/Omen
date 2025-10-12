from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.mem0_tools import MEM0_TOOLS
from tools.misc_tools import get_current_datetime
from .prompt import MEMORY_AGENT_SYSTEM_PROMPT, MEMORY_AGENT_HANDOFF_INSTRUCTIONS


config = AGENT_CONFIGS["memory_agent"]
instructions: str = MEMORY_AGENT_SYSTEM_PROMPT
MEM0_TOOLS += [get_current_datetime]

memory_agent = my_agent(
    agent_name="Memory Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=MEMORY_AGENT_HANDOFF_INSTRUCTIONS,
    tools=MEM0_TOOLS,
)
