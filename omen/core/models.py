"""Model construction: LiteLLM (Ollama / OpenAI-compatible) behind the Agents SDK."""

from __future__ import annotations

from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel

from omen.config import ModelConfig


def make_model(config: ModelConfig) -> LitellmModel:
    return LitellmModel(model=config.model, base_url=config.base_url, api_key=config.api_key)


def make_settings(config: ModelConfig) -> ModelSettings:
    return ModelSettings(
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        parallel_tool_calls=False,
        include_usage=True,
        extra_body=config.extra_body or None,
    )
