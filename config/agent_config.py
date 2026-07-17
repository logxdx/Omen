import os
from dotenv import load_dotenv

load_dotenv()

# Global max turns for agent interactions
MAX_TURNS = 20

# Online or Local
LOCAL = True

# Individual configurations for each agent
LOCAL_MODEL = "local"
LOCAL_CONFIG = {
    "PERSONALITY": "jarvis",
    "triage_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("TRIAGE_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "web_search_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("WEB_SEARCH_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "filesystem_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("FILESYSTEM_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "ideation_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("IDEATION_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "study_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("STUDY_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "analysis_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("ANALYSIS_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "context_manager_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "resume_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("RESUME_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "tts_summarizer": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": "lfm2.5",
    },
    "scraper": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
}

# Individual configurations for each agent
ONLINE_CONFIG = {
    "PERSONALITY": "jarvis",
    "triage_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("TRIAGE_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
    "web_search_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("WEB_SEARCH_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
    "filesystem_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("FILESYSTEM_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
    "ideation_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("IDEATION_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
    "study_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("STUDY_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
    "analysis_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("ANALYSIS_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
    "context_manager_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
    "resume_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("RESUME_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
    "tts_summarizer": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": "zai-glm-4.7",
    },
    "scraper": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("STUDY_API_KEY"),
        "MODEL_NAME": "openai/zai-glm-4.7",
    },
}

# Select configuration based on environment
AGENT_CONFIGS = LOCAL_CONFIG if LOCAL else ONLINE_CONFIG
