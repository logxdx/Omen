import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MEMORY_STORE_PATH = Path(__file__).parent.parent / "memory_store"
VECTOR_STORE_PATH = MEMORY_STORE_PATH / "vector_store"
GRAPH_STORE_PATH = MEMORY_STORE_PATH / "graph_store"

MEMORY_STORE_PATH.mkdir(parents=True, exist_ok=True)
VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)
GRAPH_STORE_PATH.mkdir(parents=True, exist_ok=True)


EMBEDDING_DIMS = 1024
MEM0_CONFIG = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "vector_memory.db",
            "path": f"{MEMORY_STORE_PATH}/vector_store",
        },
    },
    "graph_store": {
        "provider": "kuzu",
        "config": {"db": f"{MEMORY_STORE_PATH}/graph_store/graph_memory.db"},
    },
    "llm": {
        "provider": "groq",
        "config": {
            "model": "openai/gpt-oss-120b",
            "api_key": os.getenv("GROQ_API_KEY"),
            "max_tokens": 4096,
            "temperature": 0.1,
        },
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "qwen3-embed",
            "embedding_dims": EMBEDDING_DIMS,
            "api_key": "ollama",
            "openai_base_url": "http://localhost:11434/v1",
        },
    },
    "version": "v1.1",
}
