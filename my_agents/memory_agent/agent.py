from config.agent_config import AGENT_CONFIGS
from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel

from tools.memory_tools import memory_add, memory_search, memory_summary, memory_get_all
from tools.misc_tools import get_current_datetime
from .prompt import MEMORY_AGENT_PROMPT

config = AGENT_CONFIGS["memory_agent"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME = config["MODEL_NAME"]

litellm_model = LitellmModel(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL)


def create_memory_agent(handoffs=None):
    if handoffs is None:
        handoffs = []
    return Agent(
        name="Memory Agent",
        instructions=MEMORY_AGENT_PROMPT,
        model=litellm_model,
        handoffs=handoffs,
        tools=[
            memory_add,
            memory_search,
            memory_summary,
            memory_get_all,
            get_current_datetime,
        ],
    )