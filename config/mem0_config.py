import os
from dotenv import load_dotenv
load_dotenv()

EMBEDDING_DIMS = 768
MEM0_CONFIG = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "vector_memory.db",
            "path": "agent_memory",
        },
    },
    "graph_store": {"provider": "kuzu", "config": {"db": "./agent_memory/graph_memory.db"}},
    "llm": {
        "provider": "groq",
        "config": {
            "model": "openai/gpt-oss-20b",
            "api_key": os.getenv("GROQ_API_KEY"),
            # "openai_base_url": os.getenv("GROQ_BASE_URL"),
        },
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "embeddinggemma",
            "embedding_dims": EMBEDDING_DIMS,
            "api_key": "ollama",
            "openai_base_url": "http://localhost:11434/v1",
        },
    },
    "version": "v1.1",
}
