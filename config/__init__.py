from rich.theme import Theme

VERSION = "2.0.0"

# Tools the orchestrator may use without prompting.
ALLOWED_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
    "Agent",  # subagent invocation ("Task" on older CLI versions)
    "Task",
]

THEME = Theme(
    {
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
        "user": "bright_blue bold",
        "assistant": "bright_white",
        "tool": "bright_magenta bold",
    }
)
