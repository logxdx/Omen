import os
from dotenv import load_dotenv

load_dotenv()

# Global max turns for agent interactions
MAX_TURNS = 20

# Online or Local
LOCAL = False

# Individual configurations for each agent
LOCAL_MODEL = "qwen3:8b"
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
    "memory_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("MEMORY_API_KEY"),
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
    "google_workspace_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("GOOGLE_WORKSPACE_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    "tts_summarizer": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": f"lfm2.5",
    },
    "scraper": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": f"openai/lfm2.5",
    },
}

# Individual configurations for each agent
ONLINE_CONFIG = {
    "PERSONALITY": "jarvis",
    "triage_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("TRIAGE_API_KEY"),
        "MODEL_NAME": "openai/qwen-3-235b-a22b-instruct-2507",
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
    "ideation_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("IDEATION_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "study_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("STUDY_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
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
    "context_manager_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "resume_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("RESUME_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "google_workspace_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("GOOGLE_WORKSPACE_API_KEY"),
        "MODEL_NAME": "openai/gpt-oss-120b",
    },
    "tts_summarizer": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": "lfm2.5",
    },
    "scraper": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("STUDY_API_KEY"),
        "MODEL_NAME": "openai/lfm2.5",
    },
}

# Select configuration based on environment
AGENT_CONFIGS = LOCAL_CONFIG if LOCAL else ONLINE_CONFIG
