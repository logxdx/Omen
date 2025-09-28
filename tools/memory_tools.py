from agents import function_tool

"""Tool wrappers exposing the shared mem0 memory layer to agents.
Each tool is intentionally small and returns plain serializable data.
"""
from tools.utils.mem0_memory import (
    add_memory,
    search_memories,
    delete_memory,
    update_memory,
    history_memory,
    get_all_memories,
)


@function_tool
def memory_add(text: str, user_id: str = "logx") -> str:
    """Add a new memory fact / message to the shared memory layer.

    Args:
        text: Memory content.
        user_id: User identifier (default: "logx").
    Returns:
        Result dict from mem0 add call.
    """
    return add_memory(text, user_id=user_id)


@function_tool
def memory_search(query: str, user_id: str = "logx", limit: int = 5) -> str:
    """Semantic search over stored memories.

    Args:
        query: Search query text.
        user_id: User identifier (default: "logx").
        limit: Max number of results.
        use_graph: Whether to include graph relations in the output.
    Returns:
        List of memory entries.
    """
    return search_memories(query, user_id=user_id, limit=limit)


@function_tool
def memory_delete(memory_id: str) -> str:
    """Delete a memory entry by its ID.

    Args:
        memory_id: The ID of the memory to delete.
    Returns:
        Result dict from mem0 delete call.
    """
    return delete_memory(memory_id=memory_id)


@function_tool
def memory_update(memory_id: str, data: str) -> str:
    """Update a memory entry by its ID.

    Args:
        memory_id: The ID of the memory to update.
        data: The new data to update the memory with.
    Returns:
        Result dict from mem0 update call.
    """
    return update_memory(memory_id=memory_id, data=data)


@function_tool
def memory_history(memory_id: str) -> str:
    """Retrieve the history of a memory entry by its ID.

    Args:
        memory_id: The ID of the memory to retrieve history for.
    Returns:
        Result dict from mem0 history call.
    """
    return history_memory(memory_id=memory_id)


@function_tool
def memory_get_all(user_id: str = "logx") -> str:
    """Get all memories for a user (may be large).

    Args:
        user_id: User identifier (default: "logx").
        use_graph: Whether to include graph relations in the output.
    Returns:
        All memory entries for the user.
    """
    return get_all_memories(user_id=user_id)
