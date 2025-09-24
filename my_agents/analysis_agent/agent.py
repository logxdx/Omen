from base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.python_tools import execute_code
from tools.misc_tools import get_current_datetime
from .prompt import ANALYSIS_AGENT_SYSTEM_PROMPT, ANALYSIS_AGENT_HANDOFF_INSTRUCTIONS


config = AGENT_CONFIGS["analysis_agent"]
instructions: str = ANALYSIS_AGENT_SYSTEM_PROMPT

analysis_agent = my_agent(
    agent_name="Analysis Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=ANALYSIS_AGENT_HANDOFF_INSTRUCTIONS,
    tools=[
        execute_code,
        get_current_datetime,
    ],
)
