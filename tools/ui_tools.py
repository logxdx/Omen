from agents import function_tool

from config import ui_config


@function_tool
def skip_turn():
    """
    Set the SKIP_TURN flag to True.
    """
    ui_config.SKIP_TURN = True
    return "Turn skipped."


@function_tool
def quit_session():
    """
    Set the QUIT_SESSION flag to True.
    """
    ui_config.QUIT_SESSION = True
    return "Session quitting."


@function_tool
def clear_conversation_history():
    """
    Clear the conversation history.
    """
    ui_config.CONVERSATION_HISTORY.clear()
    return "Conversation history cleared."


@function_tool
def change_interaction_mode(new_mode: str):
    """
    Change the interaction mode.
    Args:
        new_mode (str): The new interaction mode to set. ("text" or "voice")
    """
    ui_config.INTERACTION_MODE = new_mode
    return f"Interaction mode changed to {new_mode}."


@function_tool
def change_heirarchy_mode(new_mode: str):
    """
    Change the heirarchy mode.
    Args:
        new_mode (str): The new heirarchy mode to set. ("managerial" or "collaborative")
    """
    ui_config.HEIRARCHY_MODE = new_mode
    return f"Heirarchy mode changed to {new_mode}."


@function_tool
def use_context_manager(enable: bool):
    """
    Enable or disable the context manager.
    Args:
        enable (bool): True to enable, False to disable.
    """
    ui_config.USE_CONTEXT_MANAGER = enable
    return f"Context manager set to {enable}."


UI_TOOLS = [
    skip_turn,
    quit_session,
    clear_conversation_history,
    change_interaction_mode,
    change_heirarchy_mode,
    use_context_manager,
]
