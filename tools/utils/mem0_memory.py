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
    result = m.add(messages=text, user_id=user_id, metadata=metadata)
    return json.dumps(result, indent=2)


def search_memories(query: str, user_id: str = "logx", limit: int = 20) -> str:
    """Search memories relevant to query (simple wrapper) ensuring list[dict] return."""

    m = get_memory()
    search_results = m.search(query, user_id=user_id)
    formatted_output = ""
    results = search_results.get("results", [])
    if results:
        formatted_output += "MEMORIES:\n"
        for idx, res in enumerate(results[:limit], 1):
            formatted_output += f"{idx}. {res['memory']} | Score: {res['score']} | Created: {res['created_at']} | Updated: {res['updated_at']}\n"

    relations = search_results.get("relations", [])
    if relations:
        formatted_output += "\nRELATIONS:\n"
        for idx, relation in enumerate(relations[:limit], 1):
            formatted_output += f"{idx}. {relation['source']} ->  {relation['relationship']} -> {relation['destination']}\n"

    return formatted_output


def get_all_memories(user_id: str = "logx") -> str:
    m = get_memory()
    result = m.get_all(user_id=user_id)
    return json.dumps(result, indent=2)


def summarize_user_memories(user_id: str = "logx") -> str:
    """Return a textual summary of stored memories (simple heuristic)."""
    results = get_all_memories(user_id=user_id)
    if not results:
        return "No memories stored yet."
    lines = ["Stored memories summary:"]
    return "\n".join(lines)


if __name__ == "__main__":
    # Simple test / demo
    mem = get_memory()
    print("Memory instance:", mem.api_version)

    print("Adding memory...")
    res = add_memory(
        [
            {
                "role": "user",
                "content": "I like pizzas, burgers, hot salad, green veggies and fruits too.",
            }
        ],
        user_id="testuser",
    )
    print("Add result:", res)

    print("Searching memories...")
    search_res = search_memories(
        "What healthy snacks should I have right now?", user_id="testuser", limit=3
    )
    print("Search results:", search_res)

    print("All memories:")
    all_mem = get_all_memories(user_id="testuser")
    print(all_mem)

    print("Memory summary:")
    summary = summarize_user_memories(user_id="testuser")
    print(summary)
