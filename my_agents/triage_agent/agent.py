from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from tools.misc_tools import get_current_datetime
from config.agent_personality import get_personality
from .prompt import TRIAGE_AGENT_SYSTEM_PROMPT, TRIAGE_HANDOFF_INSTRUCTIONS

config = AGENT_CONFIGS["triage_agent"]
name, personality = get_personality()
instructions: str = personality + "\n\n" + TRIAGE_AGENT_SYSTEM_PROMPT

triage_agent = my_agent(
    agent_name=name.capitalize() + " (Orchestrator)",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=TRIAGE_HANDOFF_INSTRUCTIONS,
    tools=[
        get_current_datetime,
    ],
)
