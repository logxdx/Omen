import os
from dotenv import load_dotenv

load_dotenv()

# Only the TTS summarizer still needs a local OpenAI-compatible endpoint.
# Everything else runs through the Claude Agent SDK.
AGENT_CONFIGS = {
    "tts_summarizer": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("CONTEXT_API_KEY"),
        "MODEL_NAME": "lfm2.5",
    },
}
