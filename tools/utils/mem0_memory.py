"""Shared mem0 memory layer for all agents.

Located in tools/ so it can be treated like other tool infrastructure.
Provides a singleton mem0 Memory instance plus helper functions.
"""

from __future__ import annotations

import json
from threading import Lock
from typing import Any, Dict, Optional

from mem0 import Memory
from config.mem0_config import MEM0_CONFIG

_memory_instance: Optional[Memory] = None
_lock = Lock()


def get_memory() -> Memory:
    """Return a shared Memory instance (lazy init)."""
    global _memory_instance
    if _memory_instance is None:
        with _lock:
            if _memory_instance is None:  # double-checked locking
                _memory_instance = Memory.from_config(MEM0_CONFIG)
    return _memory_instance


def add_memory(
    text: str | list[dict[str, str]],
    user_id: str = "logx",
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Add a memory entry.

    Args:
        text: The memory text / fact / message to store.
        user_id: Optional user identifier to scope memories.
        metadata: Optional additional metadata.
    Returns:
        Result dict from mem0 add.
    """
    m = get_memory()
    add_result = m.add(messages=text, user_id=user_id, metadata=metadata)

    formated_output = ""
    for result in add_result.get("results", []):
        formated_output += f"{result.get("event", "")}: {result.get("memory", "")}\n"

    relations: dict = add_result.get("relations", {})  # type: ignore
    if relations:
        for relation in relations.get("added_entities", []):
            relation = relation[0]
            formated_output += f"Relation added: {relation.get("source", "")} -> {relation.get("relationship", "")} -> {relation.get("target", "")}\n"
        for relation in relations.get("deleted_relations", []):
            relation = relation[0]
            formated_output += f"Relation deleted: {relation.get("source", "")} -> {relation.get("relationship", "")} -> {relation.get("target", "")}\n"

    return formated_output if formated_output else "No changes made."


def search_memories(query: str, user_id: str = "logx", limit: int = 20) -> str:
    """Search memories relevant to query (simple wrapper) ensuring list[dict] return."""

    m = get_memory()
    search_results = m.search(query, user_id=user_id)
    formatted_output = ""
    results = search_results.get("results", [])
    if results:
        formatted_output += "MEMORIES:\n"
        for idx, res in enumerate(results[:limit], 1):
            formatted_output += f"{idx}. {res['memory']} | Created: {res['created_at']} | Updated: {res['updated_at']}\n"

    relations: list[dict] = search_results.get("relations", [])
    if relations:
        formatted_output += "\nRELATIONS:\n"
        for idx, relation in enumerate(relations[:limit], 1):
            formatted_output += f"{idx}. {relation['source']} ->  {relation['relationship']} -> {relation['destination']}\n"

    return formatted_output


def get_all_memories(user_id: str = "logx") -> str:
    m = get_memory()
    result = m.get_all(user_id=user_id)
    formatted_output = ""
    for res in result.get("results", []):
        if res.get("memory"):
            formatted_output += f"Memory: {res.get("memory")} "
        if res.get("created_at"):
            formatted_output += f"| Created: {res.get("created_at")} "
        if res.get("updated_at"):
            formatted_output += f"| Updated: {res.get("updated_at")} "
        if res.get("metadata"):
            formatted_output += f"| Metadata: {json.dumps(res.get("metadata"))}\n"

    for res in result.get("relations", []):
        formatted_output += f"Relation: {res.get("source", "")} -> {res.get("relationship", "")} -> {res.get("target", "")}\n"

    return formatted_output if formatted_output else "No memories found."

