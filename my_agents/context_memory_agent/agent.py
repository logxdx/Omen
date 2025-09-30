from my_agents.base_agent import my_agent, agent_config
from config.agent_config import AGENT_CONFIGS
from tools.context_manager_tools import (
    save_context_topic,
    load_context_topic,
    list_context_topics,
    update_context_content,
    delete_context_topic,
)
from .prompt import CONTEXT_MANAGER_AGENT_SYSTEM_PROMPT

config = AGENT_CONFIGS["context_manager_agent"]
instructions: str = CONTEXT_MANAGER_AGENT_SYSTEM_PROMPT

context_agent = my_agent(
    agent_name="Context Manager Agent",
    config=agent_config(**config),
    instructions=instructions,
    tools=[
        save_context_topic,
        load_context_topic,
        list_context_topics,
        update_context_content,
        delete_context_topic,
    ],
)
