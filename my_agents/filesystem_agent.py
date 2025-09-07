import os
import datetime
from dotenv import load_dotenv
from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel

from tools.tools import (
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
    get_current_datetime,
)

load_dotenv()

BASE_URL = os.getenv("CEREBRAS_BASE_URL")
API_KEY = os.getenv("CEREBRAS_API_KEY")
MODEL_NAME = "openai/qwen-3-235b-a22b-instruct-2507"

litellm_model = LitellmModel(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL)


FILESYSTEM_AGENT_PROMPT = f"""
You are a filesystem management specialist agent. You operate in your root filesystem.

CORE FUNCTIONS:
1. Read files and directories
2. Write and create new files
3. List directory contents and file information
4. Delete files and directories when requested
5. Create directories
6. Move and copy files
7. Manage file organization and structure
8. Edit specific sections of files
9. Append content to existing files

FILE OPERATIONS:
- list_files(path): List directory contents
- read_file(path): Read file contents
- write_file(path, content): Create/write files
- edit_file_section(path, original_section, new_content): Edit specific sections of files
- append_to_file(path, content): Append content to files without overwriting
- create_directory(path): Create directories
- delete_file(path): Remove files
- delete_directory(path): Remove directories
- move_file(src, dst): Move files
- copy_file(src, dst): Copy files

BEST PRACTICES:
- Provide clear error messages for failed operations
- Organize files in logical directory structures
- Confirm destructive operations before proceeding
- Report file operations status clearly
- Use targeted editing when only specific sections need changes
- Use append operations for incremental content addition

RESPONSE FORMAT:
- Clearly state what operation was performed
- Show file paths relative to root
- Include success/failure status
- Provide helpful context about file operations

When users request file operations, data storage, file management, or local file tasks, use your filesystem capabilities to help them efficiently and securely.

## Handoff Options
You can handoff to other agents for collaborative tasks:
- **web_search_agent**: For researching information to include in files or finding online resources
- **ideation_agent**: For brainstorming file organization, creative content creation, or conceptual discussions
- **Vanessa (triage_agent)**: For routing complex requests involving multiple capabilities
"""


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
