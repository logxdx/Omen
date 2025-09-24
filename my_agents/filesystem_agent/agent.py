from base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.filesystem_tools import (
    list_files,
    read_file,
    write_file,
    edit_file_section,
    append_to_file,
    delete_file,
    create_directory,
    delete_directory,
    move_file,
    copy_file,
)
from tools.misc_tools import get_current_datetime
from .prompt import (
    FILESYSTEM_AGENT_SYSTEM_PROMPT,
    FILESYSTEM_AGENT_HANDOFF_INSTRUCTIONS,
)


config = AGENT_CONFIGS["filesystem_agent"]
instructions: str = FILESYSTEM_AGENT_SYSTEM_PROMPT

filesystem_agent = my_agent(
    agent_name="Filesystem Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=FILESYSTEM_AGENT_HANDOFF_INSTRUCTIONS,
    tools=[
        list_files,
        read_file,
        write_file,
        edit_file_section,
        append_to_file,
        create_directory,
        delete_file,
        delete_directory,
        move_file,
        copy_file,
        get_current_datetime,
    ],
)
