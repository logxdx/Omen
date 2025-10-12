"""
RAG (Retrieval-Augmented Generation) Configuration

Centralized configuration for all RAG-related components including
document parsing, chunking, embeddings, and storage settings.
"""

import os
from pathlib import Path
from typing import Dict, Any

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# =============================================================================
# API CONFIGURATION
# =============================================================================

# OpenAI API Configuration
OPENAI_CONFIG = {
    "api_key": os.getenv("OPENAI_API_KEY"),
    "base_url": os.getenv("OPENAI_BASE_URL"),  # Optional: for custom endpoints
    "organization": os.getenv("OPENAI_ORGANIZATION"),  # Optional
}

# Validate required API key
if not OPENAI_CONFIG["api_key"]:
    raise ValueError("OPENAI_API_KEY environment variable is required")


def get_openai_client_config() -> Dict[str, Any]:
    """Get OpenAI client configuration for creating clients"""
    config = {
        "api_key": OPENAI_CONFIG["api_key"],
    }

    if OPENAI_CONFIG["base_url"]:
        config["base_url"] = OPENAI_CONFIG["base_url"]

    if OPENAI_CONFIG["organization"]:
        config["organization"] = OPENAI_CONFIG["organization"]

    return config


# =============================================================================
# RAG INTERFACE CONFIGURATION
# =============================================================================

# Default paths for RAG storage
RAG_DEFAULT_PATHS = {
    "chroma_db": "./chroma_db",
    "document_store": "./document_store",
    "collection_name": "documents",
}

# Default chunking strategy
DEFAULT_CHUNKING_STRATEGY = "layout_aware"

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

# =============================================================================
# EMBEDDING CONFIGURATION
# =============================================================================

# OpenAI Embedding Configuration
EMBEDDING_CONFIG = {
    "model": DEFAULT_EMBEDDING_MODEL,
    "batch_size": 100,
    "dimensions": 1536,  # text-embedding-3-small dimensions
    "encoding_format": "float",
}

# Supported embedding models and their configurations
SUPPORTED_EMBEDDING_MODELS = {
    "text-embedding-3-small": {
        "dimensions": 1536,
        "max_tokens": 8191,
    },
    "text-embedding-3-large": {
        "dimensions": 3072,
        "max_tokens": 8191,
    },
    "text-embedding-ada-002": {
        "dimensions": 1536,
        "max_tokens": 8191,
    },
}

# =============================================================================
# CHUNKING CONFIGURATION
# =============================================================================

# Default chunk sizes and overlaps for different strategies
CHUNKING_DEFAULTS = {
    "character": {
        "chunk_size": 1000,
        "overlap": 100,
    },
    "word": {
        "chunk_size": 200,
        "overlap": 50,
    },
    "sentence": {
        "chunk_size": 5,
        "overlap": 2,
    },
    "markdown": {
        "chunk_size": 5,  # Not used in layout-aware
        "overlap": 2,     # Not used in layout-aware
    },
    "layout_aware": {
        "chunk_size": None,  # Not used in layout-aware chunking
        "overlap": None,     # Not used in layout-aware chunking
        "min_chunk_length": 200,  # Minimum characters for a chunk
    },
}

# Supported chunking strategies
SUPPORTED_CHUNKING_STRATEGIES = [
    "character",
    "word",
    "sentence",
    "markdown",
    "layout_aware"
]

# =============================================================================
# DOCLING PARSER CONFIGURATION
# =============================================================================

# Docling PDF Pipeline Options
DOCLING_PIPELINE_OPTIONS = {
    "do_ocr": True,
    "do_table_structure": True,
    "table_mode": "accurate",  # "accurate" or "fast"
    "do_formula_enrichment": True,
    "do_code_enrichment": True,
    "generate_picture_images": True,
    "generate_page_images": False,  # Save space
}

# Supported input formats for Docling
DOCLING_SUPPORTED_FORMATS = [
    "pdf",
    "docx",
    "xlsx",
    "pptx",
    "html",
    "htm",
]

# =============================================================================
# CHROMADB VECTOR STORE CONFIGURATION
# =============================================================================

# ChromaDB client settings
CHROMADB_SETTINGS = {
    "anonymized_telemetry": False,
}

# Vector store quantization settings
VECTOR_STORE_QUANTIZATION = {
    "type": "scalar",
    "scalar": {
        "type": "INT8",
        "quantile": 0.99,
    }
}

# Distance metric for similarity search
VECTOR_DISTANCE_METRIC = "cosine"

# =============================================================================
# DOCUMENT STORE CONFIGURATION
# =============================================================================

# Document store file structure
DOCUMENT_STORE_STRUCTURE = {
    "documents_dir": "documents",
    "metadata_dir": "metadata",
    "file_extension": ".md",
    "metadata_extension": ".json",
}

# =============================================================================
# SEARCH CONFIGURATION
# =============================================================================

# Default search parameters
SEARCH_DEFAULTS = {
    "k": 5,  # Number of results to return
    "search_type": "hybrid",  # "semantic", "text", or "hybrid"
    "min_score_threshold": 0.0,  # Minimum similarity score
}

# Hybrid search weights (semantic vs text)
HYBRID_SEARCH_WEIGHTS = {
    "semantic_weight": 0.7,
    "text_weight": 0.3,
}

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# RAG logging configuration
RAG_LOGGING_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "handlers": ["console"],
}

# =============================================================================
# PERFORMANCE CONFIGURATION
# =============================================================================

# Performance tuning parameters
PERFORMANCE_CONFIG = {
    "max_workers": 4,  # For parallel processing
    "batch_size_embeddings": 100,
    "max_retries": 3,
    "retry_delay": 1.0,  # seconds
    "timeout": 300,  # seconds for long operations
}

# Memory management
MEMORY_CONFIG = {
    "max_chunk_content_length": 10000,  # characters
    "cleanup_temp_files": True,
    "cache_embeddings": False,  # Experimental
}

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_embedding_config(model_name: str = None) -> Dict[str, Any]:
    """Get embedding configuration for a specific model"""
    model = model_name or DEFAULT_EMBEDDING_MODEL
    if model not in SUPPORTED_EMBEDDING_MODELS:
        raise ValueError(f"Unsupported embedding model: {model}")

    config = EMBEDDING_CONFIG.copy()
    config.update(SUPPORTED_EMBEDDING_MODELS[model])
    return config


def get_chunking_config(strategy: str = None) -> Dict[str, Any]:
    """Get chunking configuration for a specific strategy"""
    strategy = strategy or DEFAULT_CHUNKING_STRATEGY
    if strategy not in SUPPORTED_CHUNKING_STRATEGIES:
        raise ValueError(f"Unsupported chunking strategy: {strategy}")

    return CHUNKING_DEFAULTS[strategy]


def get_rag_paths(base_path: str = None) -> Dict[str, str]:
    """Get RAG storage paths, optionally relative to a base path"""
    paths = RAG_DEFAULT_PATHS.copy()

    if base_path:
        base = Path(base_path)
        paths["chroma_db"] = str(base / paths["chroma_db"])
        paths["document_store"] = str(base / paths["document_store"])

    return paths


def validate_config() -> bool:
    """Validate the RAG configuration"""
    try:
        # Check required environment variables
        required_env_vars = ["OPENAI_API_KEY"]
        for var in required_env_vars:
            if not os.getenv(var):
                print(f"Warning: Required environment variable {var} not set")

        # Validate API configuration
        if not OPENAI_CONFIG["api_key"]:
            raise ValueError("OpenAI API key is required but not configured")

        # Validate embedding model
        if DEFAULT_EMBEDDING_MODEL not in SUPPORTED_EMBEDDING_MODELS:
            raise ValueError(f"Invalid default embedding model: {DEFAULT_EMBEDDING_MODEL}")

        # Validate chunking strategy
        if DEFAULT_CHUNKING_STRATEGY not in SUPPORTED_CHUNKING_STRATEGIES:
            raise ValueError(f"Invalid default chunking strategy: {DEFAULT_CHUNKING_STRATEGY}")

        return True

    except Exception as e:
        print(f"Configuration validation failed: {e}")
        return False


# Validate configuration on import
if not validate_config():
    print("Warning: RAG configuration validation failed. Some features may not work correctly.")