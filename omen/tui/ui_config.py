from agents import TResponseInputItem
from rich.theme import Theme

# Version
Version = "1.4.0"

CONVERSATION_HISTORY: list[TResponseInputItem] = []

# CONSTANTS FOR VOICE MODE
SKIP_TURN: bool = False
QUIT_SESSION: bool = False
INTERACTION_MODE: str = "text"
USE_CONTEXT_MANAGER: bool = False

AGENT_THEME = Theme(
    {
        # General
        "info": "cyan",
        "warning": "yellow",
        "error": "bright_red bold",
        "success": "green",
        "dim": "dim",
        "muted": "grey50",
        "border": "grey35",
        "highlight": "bold cyan",
        "accent": "magenta",
        "accent.bold": "bold magenta",
        "title": "bold white",
        # Roles
        "user": "bright_blue bold",
        "assistant": "bright_white",
        # Tools
        "tool": "bright_magenta bold",
    }
)
