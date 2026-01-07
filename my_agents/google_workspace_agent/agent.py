from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.google_tools import (
    list_calendar_events,
    create_calendar_event,
    read_recent_emails,
    create_draft_reply
)
from tools.misc_tools import get_current_datetime
from .prompt import GOOGLE_WORKSPACE_AGENT_SYSTEM_PROMPT, GOOGLE_WORKSPACE_HANDOFF_INSTRUCTIONS

config = AGENT_CONFIGS["google_workspace_agent"]
instructions: str = GOOGLE_WORKSPACE_AGENT_SYSTEM_PROMPT
TOOLS = [
    list_calendar_events,
    create_calendar_event,
    read_recent_emails,
    create_draft_reply,
    get_current_datetime
]

google_workspace_agent = my_agent(
    agent_name="Google Workspace Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=GOOGLE_WORKSPACE_HANDOFF_INSTRUCTIONS,
    tools=TOOLS,
)
