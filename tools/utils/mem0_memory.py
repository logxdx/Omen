"""Shared mem0 memory layer for all agents.
Located in tools/ so it can be treated like other tool infrastructure.
Provides a singleton mem0 Memory instance plus helper functions.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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


def memory_add(
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
    try:
        add_result = m.add(messages=text, user_id=user_id, metadata=metadata)
    except Exception as e:
        return f"Error adding memory: {str(e)}"

    formated_output = ""
    results = add_result.get("results", [])
    if results:
        for result in results:
            formated_output += f"ID: {result.get("id", "")} | {result.get("event", "")}: {result.get("memory", "")}\n"

    relations: dict = add_result.get("relations", {})  # type: ignore
    if relations:
        for relation in relations.get("added_entities", []):
            relation = relation[0]
            formated_output += f"Relation added: {relation.get("source", "")} -> {relation.get("relationship", "")} -> {relation.get("target", "")}\n"
        for relation in relations.get("deleted_relations", []):
            relation = relation[0]
            formated_output += f"Relation deleted: {relation.get("source", "")} -> {relation.get("relationship", "")} -> {relation.get("target", "")}\n"

    return formated_output if formated_output else "No changes made."


def memory_search(query: str, user_id: str = "logx", limit: int = 5) -> str:
    """Search memories relevant to query (simple wrapper) ensuring list[dict] return."""

    m = get_memory()
    try:
        search_results = m.search(query, user_id=user_id)
    except Exception as e:
        return f"Error searching memories: {str(e)}"

    formatted_output = ""
    results = search_results.get("results", [])
    if results:
        formatted_output += "MEMORIES:\n---\n"
        for idx, res in enumerate(results[:limit], 1):
            formatted_output += f"{str(idx).rjust(3)}. ID: {res['id']}\n     Memory: {res['memory']}\n     Created: {res['created_at']}\n     Updated: {res['updated_at']}\n     Metadata: {json.dumps(res.get('metadata', {}))}\n\n"

    relations: list[dict] = search_results.get("relations", [])
    if relations:
        formatted_output += "\nRELATIONS:\n---\n"
        for idx, relation in enumerate(relations[:limit], 1):
            formatted_output += f"{str(idx).rjust(3)}. {relation['source']} ->  {relation['relationship']} -> {relation['destination']}\n"

    return formatted_output if formatted_output else "No relevant memories found."


def memory_delete(memory_id: str) -> str:
    """Delete a memory entry by ID.

    Args:
        memory_id: The ID of the memory to delete.
    Returns:
        Result dict from mem0 delete.
    """
    m = get_memory()
    try:
        delete_result = m.delete(memory_id=memory_id)
        return f"ID: {memory_id} {delete_result.get('message', '')}"
    except Exception as e:
        return f"Error deleting memory ID {memory_id}: {str(e)}"


def memory_update(memory_id: str, data: str) -> str:
    """Update a memory entry by ID.

    Args:
        memory_id: The ID of the memory to update.
        data: The new data to update the memory with.
    """
    m = get_memory()
    try:
        update_result = m.update(memory_id=memory_id, data=data)
        return f"ID: {memory_id} {update_result.get('message', '')}"
    except Exception as e:
        return f"Error updating memory ID {memory_id}: {str(e)}"


def get_memory_history(memory_id: str) -> str:
    """Retrieve the history of a memory entry by ID.
    Args:
        memory_id: The ID of the memory to retrieve history for.
    """
    m = get_memory()
    try:
        history_result = m.history(memory_id=memory_id)
    except Exception as e:
        return f"Error retrieving history for memory ID {memory_id}: {str(e)}"

    formatted_output = ""
    for history in history_result:
        if history.get("id"):
            formatted_output += f"ID: {history.get("id")}\n"
        if history.get("old_memory"):
            formatted_output += f"Old Memory: {history.get("old_memory")}\n"
        if history.get("new_memory"):
            formatted_output += f"New Memory: {history.get("new_memory")}\n"
        if history.get("created_at"):
            formatted_output += f"Created At: {history.get("created_at")}\n"
        if history.get("updated_at"):
            formatted_output += f"Updated At: {history.get("updated_at")}\n"
        if history.get("is_deleted") is not None:
            formatted_output += f"Deleted: {history.get("is_deleted")}\n"

    return (
        formatted_output
        if formatted_output
        else "No history found for the specified memory ID."
    )


def memory_all(user_id: str = "logx") -> str:
    m = get_memory()
    try:
        all_memories = m.get_all(user_id=user_id)
    except Exception as e:
        return f"Error retrieving memories: {str(e)}"

    formatted_output = ""
    for res in all_memories.get("results", []):
        if res.get("id"):
            formatted_output += f"ID: {res.get("id")}\n"
        if res.get("memory"):
            formatted_output += f"Memory: {res.get("memory")}\n"
        if res.get("created_at"):
            formatted_output += f"Created: {res.get("created_at")}\n"
        if res.get("updated_at"):
            formatted_output += f"Updated: {res.get("updated_at")}\n"
        if res.get("metadata"):
            formatted_output += f"Metadata: {json.dumps(res.get("metadata"))}\n\n"

    for res in all_memories.get("relations", []):
        formatted_output += f"Relation: {res.get("source", "")} -> {res.get("relationship", "")} -> {res.get("target", "")}\n"

    return formatted_output if formatted_output else "No memories found."


if __name__ == "__main__":

    print("🧪 Testing Mem0 setup...")

    memory = get_memory()
    print("Memory instance:", memory.api_version)

    test_messages = [
        {"role": "user", "content": "I prefer luxury hotels with spa services."},
        {
            "role": "assistant",
            "content": "I'll remember you prefer luxury hotels with spa services for future recommendations.",
        },
    ]

    results = memory_add(
        test_messages, user_id="test_user", metadata={"category": "preferences"}
    )
    print(f"Added memories:\n---\n{results}")

    search_mems = memory_search(
        "What kind of hotels do I like?", user_id="test_user", limit=3
    )
    print(f"Searched memories:\n---\n{search_mems}")

    test_memories = memory_all(user_id="test_user")
    print(f"Retrieved memories:\n---\n{test_memories}")

    history = get_memory_history("4521a84f-0ca5-4568-806d-e756fb85bb1d")
    print(f"Memory history:\n---\n{history}")
