from config.agent_config import AGENT_CONFIGS
from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel

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
from .prompt import FILESYSTEM_AGENT_PROMPT

config = AGENT_CONFIGS["filesystem_agent"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME = config["MODEL_NAME"]

litellm_model = LitellmModel(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL)


def create_filesystem_agent(handoffs=None):
    if handoffs is None:
        handoffs = []
    return Agent(
        name="filesystem_agent",
        instructions=FILESYSTEM_AGENT_PROMPT,
        model=litellm_model,
        handoffs=handoffs,
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
