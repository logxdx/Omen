from agents import function_tool
import pathlib
from tools.utils.context_manager import MemoryToolHandler

# Initialize memory handler for context storage
context_path = pathlib.Path(__file__).parent.parent
context_path = context_path.resolve() / "memory_store"
context_path.mkdir(parents=True, exist_ok=True)
context_memory_handler = MemoryToolHandler(str(context_path))


@function_tool
def save_context_topic(
    topic_name: str, content: str, is_new_topic: bool = False
) -> str:
    """
    Save or update a conversation topic context.

    Args:
        topic_name: Name of the topic/context
        content: The context content to save
        is_new_topic: Whether this is a new topic or updating existing

    Returns:
        Success message
    """
    try:
        safe_topic = "".join(
            c for c in topic_name if c.isalnum() or c in (" ", "-", "_")
        ).replace(" ", "_")[:50]
        path = f"/memories/{safe_topic}.md"

        if is_new_topic:
            header = f"# Context: {topic_name}\n\n**Created:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        else:
            header = f"# Context: {topic_name}\n\n**Updated:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        full_content = header + content

        result = context_memory_handler.execute(
            command="create", path=path, file_text=full_content
        )
        return result.get("success", result.get("error", "Unknown error"))
    except Exception as e:
        return f"Error saving context: {e}"


@function_tool
def load_context_topic(topic_name: str) -> str:
    """
    Load a saved context topic.

    Args:
        topic_name: Name of the topic to load without extension (.md)

    Returns:
        The context content
    """
    try:
        safe_topic = "".join(
            c for c in topic_name if c.isalnum() or c in (" ", "-", "_")
        ).replace(" ", "_")[:50]
        path = f"/memories/{safe_topic}.md"

        result = context_memory_handler.execute(command="view", path=path)
        return result.get("success", result.get("error", "Context not found"))
    except Exception as e:
        return f"Error loading context: {e}"


@function_tool
def list_context_topics() -> str:
    """
    List all available context topics.

    Returns:
        List of available topics
    """
    try:
        result = context_memory_handler.execute(command="view", path="/memories")
        return result.get("success", result.get("error", "No memories found"))
    except Exception as e:
        return f"Error listing memories: {e}"


@function_tool
def update_context_content(topic_name: str, old_content: str, new_content: str) -> str:
    """
    Update specific content within a context topic.

    Args:
        topic_name: Name of the topic without the extension (.md)
        old_content: Text to replace
        new_content: New text

    Returns:
        Success message
    """
    try:
        safe_topic = "".join(
            c for c in topic_name if c.isalnum() or c in (" ", "-", "_")
        ).replace(" ", "_")[:50]
        path = f"/memories/{safe_topic}.md"

        result = context_memory_handler.execute(
            command="str_replace", path=path, old_str=old_content, new_str=new_content
        )
        return result.get("success", result.get("error", "Unknown error"))
    except Exception as e:
        return f"Error updating context: {e}"


@function_tool
def delete_context_topic(topic_name: str) -> str:
    """
    Delete a context topic.

    Args:
        topic_name: Name of the topic to delete without the extension (.md)

    Returns:
        Success message
    """
    try:
        safe_topic = "".join(
            c for c in topic_name if c.isalnum() or c in (" ", "-", "_")
        ).replace(" ", "_")[:50]
        path = f"/memories/{safe_topic}.md"

        result = context_memory_handler.execute(command="delete", path=path)
        return result.get("success", result.get("error", "Unknown error"))
    except Exception as e:
        return f"Error deleting context: {e}"


CONTEXT_TOOLS = [
    save_context_topic,
    load_context_topic,
    list_context_topics,
    update_context_content,
    delete_context_topic,
]
