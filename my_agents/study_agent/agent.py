from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.misc_tools import get_current_datetime
from .prompt import STUDY_AGENT_SYSTEM_PROMPT, STUDY_AGENT_HANDOFF_INSTRUCTIONS


config = AGENT_CONFIGS["study_agent"]
instructions: str = STUDY_AGENT_SYSTEM_PROMPT

study_agent = my_agent(
    agent_name="Study Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=STUDY_AGENT_HANDOFF_INSTRUCTIONS,
    tools=[
        get_current_datetime,
    ],
)
