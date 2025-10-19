"""
Minimal terminal UI replacement for the original Rich-based CLI.

Goals:
- Keep the same public function names so it can be a drop-in replacement.
- Use only the standard library where possible.
- Provide a smooth, minimal terminal experience: clear-screen panels, concise prompts,
  streaming updates as plain text, keyboard interrupt (Ctrl+C) to stop streams.
- Optional: Use `prompt_toolkit` if available to improve prompts (not required).

Notes:
- This file intentionally keeps the same function signatures as the original so it
  can be integrated into the existing codebase with minimal changes.
- If you want nicer colored output, install `colorama` (Windows) or use a terminal
  with ANSI color support and adjust the `COLOR_*` constants below.

Added: simple markdown rendering for panels, streaming output and history.
- Supports headings (#...), bold (**bold** / __bold__), italic (*italic* / _italic_),
  inline code (`code`), fenced code blocks (```), lists (-, *, +, 1.), horizontal rules,
  and links [text](url) (expanded inline).

This renderer is intentionally small and conservative; it aims to make typical
assistant output readable in a terminal without pulling in external dependencies.
"""

from typing import List, Tuple
import json
import os
import shutil
import threading
import asyncio
import time
import sys
import re

from openai.types.responses import (
    ResponseTextDeltaEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseReasoningSummaryTextDeltaEvent,
)
from agents import (
    Agent,
    RawResponsesStreamEvent,
    Runner,
    RunResultStreaming,
    RunItemStreamEvent,
    TResponseInputItem,
    AgentUpdatedStreamEvent,
    set_tracing_disabled,
)
from config.agent_config import Version, MAX_TURNS
from .art import get_art
from tts.PiperTTS import PiperTTS as TTS
from my_agents import context_agent

set_tracing_disabled(disabled=True)

# Terminal layout constants
CONSOLE_WIDTH = shutil.get_terminal_size((120, 20)).columns
SEPARATOR = "=" * min(120, CONSOLE_WIDTH)

# Basic ANSI colors (safe fallback to empty strings on unsupported terminals)
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_PURPLE = "\033[35m"
COLOR_WHITE = "\033[37m"
COLOR_YELLOW = "\033[33m"
COLOR_DIM = "\033[2m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"

# If the terminal likely doesn't support ANSI (simple heuristic for Windows without termcap),
# drop colors. On many modern Windows terminals, ANSI works fine; if it doesn't, colors will
# still appear as escape codes. Decide conservatively by checking TERM env var.
# if os.name == "nt" and ("ANSICON" not in os.environ and "WT_SESSION" not in os.environ):
#     COLOR_RESET = COLOR_BOLD = COLOR_PURPLE = COLOR_WHITE = ""
#     COLOR_YELLOW = COLOR_DIM = COLOR_RED = COLOR_GREEN = ""

welcome_art = get_art()
_tts = None


def clear_screen() -> None:
    """Clears the terminal in a cross-platform way."""
    os.system("cls" if os.name == "nt" else "clear")


def centered(text: str, width: int = CONSOLE_WIDTH) -> str:
    """Return text centered in the given width."""
    return text.center(width)


# --- Simple Markdown renderer (ANSI) ---

def _process_inlines(text: str) -> str:
    """Handle inline markdown: code, bold, italic, links. Returns ANSI-formatted text."""
    if not text:
        return ""

    s = text

    # Protect already ANSI-coded sequences by working on plain text; this is minimal.
    # 1) inline code: `code`
    s = re.sub(r"`([^`]+?)`", lambda m: COLOR_YELLOW + m.group(1) + COLOR_RESET, s)

    # 2) bold: **bold** or __bold__
    s = re.sub(r"\*\*(.+?)\*\*", lambda m: COLOR_BOLD + m.group(1) + COLOR_RESET, s)
    s = re.sub(r"__(.+?)__", lambda m: COLOR_BOLD + m.group(1) + COLOR_RESET, s)

    # 3) italic: *italic* or _italic_ (avoid touching already-bold sequences)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", lambda m: COLOR_DIM + m.group(1) + COLOR_RESET, s)
    s = re.sub(r"_(.+?)_", lambda m: COLOR_DIM + m.group(1) + COLOR_RESET, s)

    # 4) links: [text](url) -> text (url)
    def _link_repl(m):
        text_part = m.group(1)
        url_part = m.group(2)
        return f"{COLOR_BOLD}{text_part}{COLOR_RESET} ({COLOR_DIM}{url_part}{COLOR_RESET})"

    s = re.sub(r"\[([^\]]+?)\]\(([^)]+?)\)", _link_repl, s)

    return s


def render_markdown(text: str) -> str:
    """A small markdown -> ANSI renderer.

    Supported constructs (practical subset):
      - ATX headings: # H1 .. ###### H6
      - Bold: **bold**, __bold__
      - Italic: *italic*, _italic_
      - Inline code: `code`
      - Fenced code blocks: ``` ... ``` (rendered in dim block)
      - Lists: -, *, +, or numbered lists
      - Horizontal rules: --- or *** on their own line
      - Links: [text](url) -> text (url)

    This intentionally keeps behaviour conservative (no HTML rendering, no tables).
    """
    if text is None:
        return ""

    s = str(text)

    # Normalize line endings and split
    lines = s.splitlines()
    out_lines: List[str] = []

    in_code_block = False
    code_block_fence = None

    for raw in lines:
        line = raw.rstrip("\n\r")

        # Fenced code blocks (```)
        fence_match = re.match(r"^(?P<fence>`{3,})(?P<lang>\w+)?\s*$", line)
        if fence_match:
            if not in_code_block:
                in_code_block = True
                code_block_fence = fence_match.group("fence")
                out_lines.append(COLOR_DIM + "--- code block ---" + COLOR_RESET)
            else:
                in_code_block = False
                code_block_fence = None
                out_lines.append(COLOR_DIM + "--- end code block ---" + COLOR_RESET)
            continue

        if in_code_block:
            # Preserve indentation for code lines
            out_lines.append(COLOR_DIM + "    " + line + COLOR_RESET)
            continue

        # Horizontal rule
        if re.match(r"^\s*([-*_]){3,}\s*$", line):
            out_lines.append(SEPARATOR)
            continue

        # ATX headings
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            level = len(h.group(1))
            content = h.group(2).strip()
            if level == 1:
                out_lines.append(COLOR_BOLD + COLOR_YELLOW + content.upper() + COLOR_RESET)
            elif level == 2:
                out_lines.append(COLOR_BOLD + COLOR_PURPLE + content + COLOR_RESET)
            else:
                out_lines.append(COLOR_BOLD + content + COLOR_RESET)
            continue

        # Lists (unordered or ordered)
        list_match = re.match(r"^\s*([-*+]|\d+\.)\s+(.*)$", line)
        if list_match:
            marker = list_match.group(1)
            content = list_match.group(2)
            out_lines.append(f"  {marker} {_process_inlines(content)}")
            continue

        # Blockquote '>' (render simply with dim prefix)
        bq = re.match(r"^\s*>\s?(.*)$", line)
        if bq:
            out_lines.append(COLOR_DIM + "> " + _process_inlines(bq.group(1)) + COLOR_RESET)
            continue

        # Default: process inline markdown in the line
        out_lines.append(_process_inlines(line))

    return "\n".join(out_lines)


# --- UI functions ---


def print_panel(title: str, body: str, border: str = SEPARATOR) -> None:
    """Print a simple panel with a title and body. The body is markdown-rendered."""
    print(border)
    print(centered(f"{COLOR_BOLD}{title}{COLOR_RESET}"))
    print(border)
    print(render_markdown(body))
    print(border)


def input_with_default(prompt_text: str, default: str) -> str:
    """Prompt with a visible default value that is used if the user presses Enter."""
    try:
        raw = input(f"{prompt_text} [{default}]: ")
    except EOFError:
        return default
    return raw.strip() or default


def get_tts():
    global _tts
    if _tts is None:
        _tts = TTS()
    return _tts


def welcome_panel():
    """Show a compact welcome screen."""
    clear_screen()
    body_lines = [
        f"{COLOR_PURPLE}{welcome_art}{COLOR_RESET}",
        "",
        f"{COLOR_BOLD}Features:{COLOR_RESET}",
        "- Web searches and information retrieval",
        "- File and filesystem management",
        "- Brainstorming and shared sketchpad",
        "- Data analysis and code execution",
        "- Study guidance and learning support",
    ]
    body = "\n".join(body_lines)
    print_panel(f"{Version}", body)


def select_hierarchy_mode() -> str:
    print("Choose your preferred interaction mode:")
    print(
        "  1) Managerial - triage agent manages interactions behind the scenes (default)"
    )
    print("  2) Collaborative - agents can handoff directly to each other")
    choice = input_with_default("Mode", "1")
    selected = "managerial" if choice == "1" else "collaborative"
    print(f"Selected: {selected}\n")
    return selected


def select_interaction_mode() -> str:
    print("Choose your preferred input/output mode:")
    print("  1) Text (default)")
    print("  2) Voice - STT + TTS")
    choice = input_with_default("Mode", "1")
    selected = "text" if choice == "1" else "voice"
    print(f"Selected: {selected}\n")
    return selected


def handle_agents_command(user_msg: str, agents: dict, agent: Agent) -> Agent:
    parts = user_msg.split()
    if len(parts) == 1:
        # list agents
        lines = ["Available agents:"]
        for key, value in agents.items():
            lines.append(f"  {key}: {str(value.name).capitalize()}")
        lines.append("Use '/agents <name>' or '/a <name>' to switch.")
        print("\n".join(lines))
    elif len(parts) == 2:
        agent_name = parts[1].lower()
        if agent_name in agents:
            agent = agents[agent_name]
            print(f"Switched to {str(agent.name).capitalize()}")
            return agent
        else:
            print(f"Unknown agent: {agent_name}")
    else:
        print("Usage: /agents or /a <name>")
    return agent


def pretty_print_history(history) -> str:
    output_lines = []

    for i, entry in enumerate(history, 1):
        role: str = entry.get("role", "") or entry.get("type", "unknown")
        content = entry.get("content", "")

        if content:
            if isinstance(content, str):
                output_lines.append(f"# {role.capitalize()}\n\n{content}\n\n")
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        if item["text"].strip() != "":
                            output_lines.append(
                                f"# {role.capitalize()}\n\n{item['text']}\n\n"
                            )
                    else:
                        output_lines.append(f"# {role.capitalize()}\n\n{item}\n\n")
            elif isinstance(content, dict):
                output_lines.append(
                    f"# {role.capitalize()}\n\n"
                    + json.dumps(content, indent=2)
                    + "\n\n"
                )
        else:
            if "name" in entry:
                name: str = entry["name"]
                if entry["name"].startswith("transfer_"):
                    name = name.replace("_", " ").capitalize()
                    output_lines.append(f"# Tool Call\n\n{name}\n\n")
                    continue
                output_lines.append(f"# Tool Call\n\n{name}\n\n")
                if "arguments" in entry:
                    args = (
                        json.loads(entry["arguments"]) if isinstance(entry["arguments"], str) else entry["arguments"]
                    )
                    output_lines.append(
                        "**Arguments:**\n\n" + json.dumps(args, indent=2) + "\n\n"
                    )
            if "output" in entry:
                output = entry["output"]
                if isinstance(output, str) and output.startswith('{"'):
                    continue
                output_lines.append("**Output:**\n" + str(output) + "\n")

    return "\n".join(output_lines)


def display_history(inputs: List[TResponseInputItem]):
    if not inputs:
        print("No conversation history available.")
        return
    history_text = pretty_print_history(inputs)
    print_panel("Conversation History", history_text)


def help_panel():
    lines = ["Available Commands:"]
    for cmd_info in COMMANDS.values():
        alias_str = " or ".join(cmd_info["aliases"])  # type: ignore
        lines.append(f"  {alias_str} - {cmd_info['description']}")
    lines.append("Use Ctrl+C to interrupt responses")
    print_panel("Help", "\n".join(lines))


# Command handlers (kept minimal)


def handle_quit(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    clear_screen()
    print("Ending session")
    return True, True, inputs, agent, agents, hierarchy_mode, interaction_mode


def handle_clear(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    welcome_panel()
    print(f"Current agent: {str(agent.name).capitalize()}")
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


def handle_history(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    display_history(inputs)
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


def handle_hierarchy(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    hierarchy_mode = select_hierarchy_mode()
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


def handle_help(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    help_panel()
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


def handle_clear_history(
    user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode
):
    inputs.clear()
    print("Conversation history cleared!")
    welcome_panel()
    print(f"Current agent: {str(agent.name).capitalize()}")
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


def handle_agents(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    agent = handle_agents_command(user_msg, agents, agent)
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


def handle_interaction(
    user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode
):
    interaction_mode = select_interaction_mode()
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


COMMANDS = {
    "help": {
        "aliases": ["/help", "/h"],
        "description": "Show this help message",
        "handler": handle_help,
    },
    "history": {
        "aliases": ["/history", "/hs"],
        "description": "Show conversation history",
        "handler": handle_history,
    },
    "agents": {
        "aliases": ["/agents", "/a"],
        "description": "List and switch agents",
        "handler": handle_agents,
    },
    "hierarchy": {
        "aliases": ["/hierarchy", "/hmode"],
        "description": "Change hierarchy mode",
        "handler": handle_hierarchy,
    },
    "interaction": {
        "aliases": ["/interaction", "/imode"],
        "description": "Change interaction mode",
        "handler": handle_interaction,
    },
    "clear": {
        "aliases": ["/clear", "/c"],
        "description": "Clear conversation",
        "handler": handle_clear,
    },
    "clear_history": {
        "aliases": ["/clear_history", "/ch"],
        "description": "Clear conversation history",
        "handler": handle_clear_history,
    },
    "quit": {
        "aliases": ["/quit", "/exit", "/q"],
        "description": "Exit the application",
        "handler": handle_quit,
    },
}


def slash_commands(
    user_msg: str,
    inputs: list[TResponseInputItem],
    agent: Agent,
    agents: dict,
    hierarchy_mode: str,
    interaction_mode: str,
) -> Tuple[bool, bool, list[TResponseInputItem], Agent, dict, str, str]:
    for cmd_info in COMMANDS.values():
        if user_msg.lower().split()[0] in [a.lower() for a in cmd_info["aliases"]]:
            return cmd_info["handler"](
                user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode
            )
    return False, False, inputs, agent, agents, hierarchy_mode, interaction_mode


async def stream_agent_response(
    agent: Agent, inputs: list[TResponseInputItem], hierarchy_mode: str
) -> Tuple[Agent, RunResultStreaming]:
    """Stream the agent's response and display a minimal live UI.

    Uses clear-screen reprints and respects Ctrl+C to interrupt.
    """
    result = Runner.run_streamed(
        starting_agent=agent, input=inputs, max_turns=MAX_TURNS
    )

    full_response = ""
    thinking_text = ""
    events_text = ""

    stop_event = threading.Event()

    # We'll handle keyboard interrupt (Ctrl+C) to set stop_event
    try:
        # Async iterate through streamed events
        async for event in result.stream_events():
            # Update response parts depending on event type
            if isinstance(event, RawResponsesStreamEvent):
                data = event.data
                if isinstance(data, ResponseTextDeltaEvent):
                    delta = data.delta
                    full_response += delta
                elif isinstance(data, ResponseReasoningTextDeltaEvent):
                    delta = data.delta
                    thinking_text += delta
                elif isinstance(data, ResponseReasoningSummaryTextDeltaEvent):
                    delta = data.delta
                    thinking_text += delta

            elif isinstance(event, RunItemStreamEvent):
                if event.name == "handoff_occured":
                    target_name = event.item.target_agent.name  # type: ignore
                    display_target = str(target_name).capitalize()
                    if hierarchy_mode == "collaborative":
                        agent = event.item.target_agent  # type: ignore
                        handoff_msg = f"Handed-off to {display_target}.\n"
                    else:
                        handoff_msg = f"Delegated to {display_target}.\n"
                    events_text += handoff_msg

                elif event.name == "tool_called":
                    tool_name = getattr(event.item.raw_item, "name", "unknown tool")
                    tool_args: str = getattr(event.item.raw_item, "arguments", "{}")
                    tool_msg = f"Tool: {tool_name}"
                    if tool_args:
                        tool_msg += (
                            f" | Args: {json.dumps(json.loads(tool_args), indent=2)}"
                        )
                    tool_msg += "\n"
                    events_text += tool_msg

                elif event.name == "tool_output":
                    tool_output = str(event.item.output).strip()  # type: ignore
                    if tool_output:
                        tool_output_msg = f"Tool output: \n---\n{tool_output}\n"
                        events_text += tool_output_msg

            elif isinstance(event, AgentUpdatedStreamEvent):
                new_agent = event.new_agent
                if new_agent.name != agent.name:
                    # notify, but don't forcibly switch here (handled by handoff event)
                    switch_msg = f"Switched to {str(new_agent.name).capitalize()}\n"
                    events_text += switch_msg

            # Redraw the minimal UI
            clear_screen()
            print(SEPARATOR)
            print(centered(f"🤖 {str(agent.name).capitalize()}"))
            print(SEPARATOR)
            # Events (top)
            print("Events:")
            print(render_markdown(events_text) or "(none)")
            print(SEPARATOR)
            # Thinking (compact)
            if thinking_text:
                print("[thinking]")
                print(render_markdown(thinking_text))
                print(SEPARATOR)
            # Main response body
            print(render_markdown(full_response))
            print(SEPARATOR)

            # Check if caller requested interruption via stop_event
            if stop_event.is_set():
                print("Interrupted by user")
                break

    except KeyboardInterrupt:
        # Allow user to press Ctrl+C to interrupt streaming
        print("\nInterrupted (Ctrl+C). Stopping stream...\n")
        stop_event.set()
    except Exception as e:
        print(f"Error while streaming from agent {agent.name}: {e}")

    return agent, result


async def run_cli(
    agents: dict[str, Agent], starting_agent: Agent, use_context_agent: bool = False
):
    tts_client: TTS = None  # type: ignore
    session_context: str = ""

    try:
        hierarchy_mode = select_hierarchy_mode()
        interaction_mode = select_interaction_mode()
    except Exception:
        raise Exception("Error selecting modes")

    agent = starting_agent
    welcome_panel()

    inputs: List[TResponseInputItem] = [
        {
            "content": "Short Intro. State your capabilities and ask how you can assist.",
            "role": "user",
        }
    ]

    agent, result = await stream_agent_response(agent, inputs, "managerial")
    inputs.clear()

    if interaction_mode == "voice":
        if not tts_client:
            tts_client = get_tts()
        try:
            tts_client.speak(str(result.final_output))
        except Exception as e:
            print(f"TTS Error: {e}")

    while True:
        if session_context and len(inputs) == 0:
            inputs.append({"content": session_context, "role": "assistant"})

        try:
            user_msg = input("You: ").strip()
        except EOFError:
            print("\nEOF received, exiting.")
            break

        if user_msg.startswith("<ml>"):
            while not user_msg.endswith("</ml>"):
                try:
                    next_line = input().strip()
                except EOFError:
                    break
                user_msg += "\n" + next_line
            user_msg = user_msg.replace("<ml>", "").replace("</ml>", "").strip()

        if not user_msg:
            continue

        quit_flag, skip, inputs, agent, agents, hierarchy_mode, interaction_mode = (
            slash_commands(
                user_msg.lower(),
                inputs,
                agent,
                agents,
                hierarchy_mode,
                interaction_mode,
            )
        )
        if quit_flag:
            if tts_client:
                try:
                    tts_client.shutdown()
                except Exception:
                    pass
            break
        if skip:
            if inputs:
                inputs.pop()
            continue

        inputs.append({"content": user_msg, "role": "user"})

        if use_context_agent:
            context_result = await Runner.run(
                starting_agent=context_agent.agent, input=inputs, max_turns=MAX_TURNS
            )

            if context_result.final_output != session_context:
                session_context = str(context_result.final_output).strip()
                print("Context updated by Context Manager Agent.")

        agent, result = await stream_agent_response(agent, inputs, hierarchy_mode)

        if interaction_mode == "voice":
            if not tts_client:
                tts_client = get_tts()
            try:
                tts_client.speak(str(result.final_output), user_query=user_msg)
            except Exception as e:
                print(f"TTS Error: {e}")

        inputs = result.to_input_list()

        if use_context_agent:
            for input_item in inputs:
                if input_item.get("type") in ["function_call", "function_call_output"]:
                    context_result = await Runner.run(
                        starting_agent=context_agent.agent,
                        input=inputs,
                        max_turns=MAX_TURNS,
                    )
                    if context_result.final_output:
                        session_context = str(context_result.final_output).strip()
                        print("Context updated by Context Manager Agent.")
                    break


if __name__ == "__main__":
    # This module is primarily a drop-in for the original app. The following is only
    # for local testing without the rest of the system available.
    print(
        "This file provides a minimal terminal UI to replace 'rich'. Import and run `run_cli` from your app."
    )
