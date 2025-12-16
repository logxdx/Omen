from agents import TResponseInputItem

# Version
Version = "1.4.0"

CONVERSATION_HISTORY: list[TResponseInputItem] = []

# CONSTANTS FOR VOICE MODE
SKIP_TURN: bool = False
QUIT_SESSION: bool = False
HEIRARCHY_MODE: str = "managerial"
INTERACTION_MODE: str = "text"
USE_CONTEXT_MANAGER: bool = False
