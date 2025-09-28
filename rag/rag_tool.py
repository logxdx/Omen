import os
from abc import ABC, abstractmethod
from typing import Any

from rag.core import RAG


class Adapter(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @abstractmethod
    def query(
        self,
        question: str,
        similarity_threshold: float | None = None,
        limit: int | None = None,
    ) -> str:
        """Query the knowledge base with a question and return the answer."""

    @abstractmethod
    def add(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Add content to the knowledge base."""


class RagTool:
    name: str = "Knowledge base"
    description: str = "A knowledge base that can be used to answer questions."
    summarize: bool = False
    similarity_threshold: float = 0.6
    limit: int = 5
    adapter: Adapter = Field(default_factory=lambda: ChromaAdapter(
        collection_name="rag_tool_collection",
        persist_directory=None,
        embedding_model="text-embedding-3-small",
        summarize=False,
        similarity_threshold=0.6,
        limit=5,
        config=None
    ))
    config: Any | None = None

    @model_validator(mode="after")
    def _set_default_adapter(self):
        if self.config is not None:
            parsed_config = self._parse_config(self.config)
            self.adapter = ChromaAdapter(
                collection_name="rag_tool_collection",
                persist_directory=parsed_config.get("persist_directory"),
                embedding_model=parsed_config.get("embedding_model", "text-embedding-3-small"),
                summarize=self.summarize,
                similarity_threshold=self.similarity_threshold,
                limit=self.limit,
                config=parsed_config.get("embedding_config")
            )

        return self

    @staticmethod
    def _parse_config(config: Any) -> dict:
        """Parse complex config format to extract provider-specific config."""
        if config is None:
            return {}

        if isinstance(config, dict) and "provider" in config:
            return config

        if isinstance(config, dict):
            if "vectordb" in config:
                vectordb_config = config["vectordb"]
                if isinstance(vectordb_config, dict) and "provider" in vectordb_config:
                    provider = vectordb_config["provider"]
                    if provider == "chromadb":
                        provider_config = vectordb_config.get("config", {})
                        embedding_config = config.get("embedding_model")
                        return {
                            "provider": provider,
                            "persist_directory": provider_config.get("persist_directory"),
                            "embedding_model": embedding_config.get("model", "text-embedding-3-small") if embedding_config else "text-embedding-3-small",
                            "embedding_config": embedding_config
                        }
                    else:
                        raise ValueError(f"Unsupported vector database provider: '{provider}'. Only chromadb is supported.")
                else:
                    return {}
            else:
                embedding_config = config.get("embedding_model")
                return {
                    "embedding_model": embedding_config.get("model", "text-embedding-3-small") if embedding_config else "text-embedding-3-small",
                    "embedding_config": embedding_config
                }
        return {}

    def add(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.adapter.add(*args, **kwargs)

    def query(
        self,
        question: str,
        similarity_threshold: float | None = None,
        limit: int | None = None,
    ) -> str:
        thresh = (
            similarity_threshold
            if similarity_threshold is not None
            else self.similarity_threshold
        )
        result_limit = limit if limit is not None else self.limit
        return f"Relevant Content:\n{self.adapter.query(question, similarity_threshold=thresh, limit=result_limit)}"


class ChromaAdapter(Adapter):
    def __init__(
        self,
        collection_name: str,
        persist_directory: str | None,
        embedding_model: str,
        summarize: bool,
        similarity_threshold: float,
        limit: int,
        config: dict | None,
    ):
        self.rag = RAG(
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedding_model=embedding_model,
            summarize=summarize,
            top_k=limit,
            embedding_config=config or {},
        )
        self.similarity_threshold = similarity_threshold
        self.limit = limit

    def query(
        self,
        question: str,
        similarity_threshold: float | None = None,
        limit: int | None = None,
    ) -> str:
        thresh = (
            similarity_threshold
            if similarity_threshold is not None
            else self.similarity_threshold
        )
        lim = limit if limit is not None else self.limit
        return self.rag.query(question, similarity_threshold=thresh, limit=lim)

    def add(self, *args: Any, **kwargs: Any) -> None:
        self.rag.add(*args, **kwargs)