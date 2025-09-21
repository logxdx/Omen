import os
from dotenv import load_dotenv

load_dotenv()

# Global max turns for agent interactions
MAX_TURNS = 20

# Individual configurations for each agent
AGENT_CONFIGS = {
    "ideation_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("IDEATION_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "web_search_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("WEB_SEARCH_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "filesystem_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("FILESYSTEM_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "study_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("STUDY_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "triage_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("TRIAGE_API_KEY"),
        "MODEL_NAME": "openai/qwen-3-235b-a22b-instruct-2507",
        "PERSONALITY": "omen",
    },
    "memory_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("MEMORY_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "analysis_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("ANALYSIS_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
}
