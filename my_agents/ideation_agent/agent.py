from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.misc_tools import get_current_datetime
from tools.filesystem_tools import (
    read_file,
    edit_file_section,
    append_to_file,
    write_file,
)
from .prompt import IDEATION_AGENT_SYSTEM_PROMPT, IDEATION_AGENT_HANDOFF_INSTRUCTIONS


config = AGENT_CONFIGS["ideation_agent"]
instructions: str = IDEATION_AGENT_SYSTEM_PROMPT

ideation_agent = my_agent(
    agent_name="Ideation Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=IDEATION_AGENT_HANDOFF_INSTRUCTIONS,
    tools=[
        read_file,
        write_file,
        edit_file_section,
        append_to_file,
        get_current_datetime,
    ],
)
