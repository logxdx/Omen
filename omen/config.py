"""Runtime configuration, read from the environment (.env).

Uses the same variables as the old `config/agent_config.py` (OLLAMA_BASE_URL,
CEREBRAS_BASE_URL, TRIAGE_API_KEY), plus OMEN_* overrides.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OMEN_HOME = Path(os.getenv("OMEN_HOME", Path.home() / ".omen"))
SESSIONS_DIR = OMEN_HOME / "sessions"

# Skill and persona folders: the repo's, then the user's own (same name overrides).
REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIRS = [REPO_ROOT / "skills", OMEN_HOME / "skills"]
PERSONAS_DIRS = [REPO_ROOT / "personas", OMEN_HOME / "personas"]
DEFAULT_PERSONA = os.getenv("OMEN_PERSONA", "omen")

# Upper bound on LLM steps per user message.
MAX_TURNS = int(os.getenv("OMEN_MAX_TURNS", "50"))

# Default cap on the text a tool returns to the model (~1k tokens).
TOOL_CONTENT_MAX_CHARS = int(os.getenv("OMEN_TOOL_MAX_CHARS", "4000"))


@dataclass
class ModelConfig:
    model: str  # LiteLLM model name, e.g. "openai/jarvis"
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.3
    max_tokens: int = 2048
    # Backend-specific request fields passed through verbatim, e.g.
    # {"chat_template_kwargs": {"enable_thinking": false}} for Qwen on llama.cpp.
    extra_body: dict = field(default_factory=dict)


def extractor_model() -> ModelConfig:
    """Model that fills UI components from text (JSON schema mode). Defaults to the main model."""
    main = main_model()
    return ModelConfig(
        model=os.getenv("OMEN_EXTRACTOR_MODEL", main.model),
        base_url=os.getenv("OMEN_EXTRACTOR_BASE_URL", main.base_url or ""),
        api_key=os.getenv("OMEN_EXTRACTOR_API_KEY", main.api_key or ""),
        temperature=0.0,
        max_tokens=800,
    )


def main_model() -> ModelConfig:
    local = os.getenv("OMEN_LOCAL", "1") != "0"
    extra_body = json.loads(os.getenv("OMEN_EXTRA_BODY", "{}"))
    api_key = os.getenv("OMEN_API_KEY") or os.getenv("TRIAGE_API_KEY")

    if local:
        return ModelConfig(
            model=os.getenv("OMEN_MODEL", "openai/jarvis"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key=api_key or "ollama",
            extra_body=extra_body,
        )
    return ModelConfig(
        model=os.getenv("OMEN_MODEL", "openai/zai-glm-4.7"),
        base_url=os.getenv("CEREBRAS_BASE_URL"),
        api_key=api_key,
        extra_body=extra_body,
    )
