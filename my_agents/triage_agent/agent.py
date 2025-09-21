from config.agent_config import AGENT_CONFIGS
from agents import Agent
from agents.extensions.models.litellm_model import LitellmModel
from tools.misc_tools import get_current_datetime
import config.agent_personality as personality
import random
from .prompt import get_triage_agent_prompt

config = AGENT_CONFIGS["triage_agent"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME = config["MODEL_NAME"]
PERSONALITY = str(config.get("PERSONALITY", "random")).upper()

# Select personality based on config
if PERSONALITY == "RANDOM":
    selected_personality = random.choice(personality.PERSONALITIES)
else:
    selected_personality = personality.PERSONALITY_DICT[PERSONALITY]

litellm_model = LitellmModel(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL)


def create_triage_agent(handoffs: list):
    return Agent(
        name=PERSONALITY.capitalize() + " (Orchestrator)",
        instructions=get_triage_agent_prompt(selected_personality),
        model=litellm_model,
        handoffs=handoffs,
        tools=[
            get_current_datetime,
        ],
    )
