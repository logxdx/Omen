from config.agent_config import AGENT_CONFIGS
from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel

from tools.python_tools import execute_code
from tools.misc_tools import get_current_datetime
from .prompt import ANALYSIS_AGENT_PROMPT

config = AGENT_CONFIGS["analysis_agent"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME = config["MODEL_NAME"]

litellm_model = LitellmModel(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL)


def create_analysis_agent(handoffs=None):
    if handoffs is None:
        handoffs = []
    return Agent(
        name="Analysis Agent",
        instructions=ANALYSIS_AGENT_PROMPT,
        model=litellm_model,
        handoffs=handoffs,
        tools=[
            execute_code,
            get_current_datetime,
        ],
    )