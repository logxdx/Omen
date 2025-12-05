from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.misc_tools import get_current_datetime
from tools.filesystem_tools import read_file, write_file, list_files
from .prompt import RESUME_AGENT_SYSTEM_PROMPT, RESUME_AGENT_HANDOFF_INSTRUCTIONS


config = AGENT_CONFIGS["resume_agent"]
instructions: str = RESUME_AGENT_SYSTEM_PROMPT

RESUME_AGENT_TOOLS = [
    read_file,
    write_file,
    list_files,
    get_current_datetime,
]

resume_agent = my_agent(
    agent_name="Resume Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=RESUME_AGENT_HANDOFF_INSTRUCTIONS,
    tools=RESUME_AGENT_TOOLS,
)
