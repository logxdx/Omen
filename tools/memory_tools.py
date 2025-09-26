from agents import function_tool

"""Tool wrappers exposing the shared mem0 memory layer to agents.
Each tool is intentionally small and returns plain serializable data.
"""
from tools.utils.mem0_memory import (
    add_memory,
    search_memories,
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
def memory_search(query: str, user_id: str = "logx", limit: int = 5, use_graph: bool = False) -> str:
    """Semantic search over stored memories.

    Args:
        query: Search query text.
        user_id: User identifier (default: "logx").
        limit: Max number of results.
        use_graph: Whether to include graph relations in the output.
    Returns:
        List of memory entries.
    """
    return search_memories(query, user_id=user_id, limit=limit, use_graph=use_graph)


@function_tool
def memory_get_all(user_id: str = "logx", use_graph: bool = False) -> str:
    """Get all memories for a user (may be large).

    Args:
        user_id: User identifier (default: "logx").
        use_graph: Whether to include graph relations in the output.
    Returns:
        All memory entries for the user.
    """
    return get_all_memories(user_id=user_id, use_graph=use_graph)
