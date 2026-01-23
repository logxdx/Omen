import re
import json

from openai.types.responses import (
    ResponseTextDeltaEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseReasoningSummaryTextDeltaEvent,
)
from agents import (
    Agent,
    AgentUpdatedStreamEvent,
    RawResponsesStreamEvent,
    Runner,
    RunConfig,
    RunResultStreaming,
    RunItemStreamEvent,
    Usage,
    set_tracing_disabled,
)
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.table import Table
from rich.text import Text

from .art import get_art
from config.agent_config import MAX_TURNS
from config import ui_config
from agent_runtime import get_agent_registry
from stt.WhisperSTT import WhisperSTT as STT
from tts.KokoroTTS import KokoroTTS as TTS
from my_agents import context_agent

set_tracing_disabled(disabled=True)

CONSOLE_WIDTH = 150
console = Console(
    theme=ui_config.AGENT_THEME, color_system="truecolor", width=CONSOLE_WIDTH
)
console.clear()

welcome_art = get_art()
stt_client: STT = None  # type: ignore
tts_client: TTS = None  # type: ignore
CURRENT_AGENT: Agent

AGENTS_REGISTRY, CURRENT_AGENT = get_agent_registry()


def setup_voice_mode():
    global tts_client, stt_client

    if tts_client is None:
        tts_client = TTS()

    if stt_client is None:
        stt_client = STT(spinner=True, on_vad_detect_start=lambda: tts_client.pause())


def welcome_panel():
    """
    Welcome Panel
    """
    console.clear()

    commands_table = Table.grid(padding=(0, 4))
    commands_table.add_column(style="accent.bold", justify="right")
    commands_table.add_column(style="assistant", justify="left")

    for cmd_info in COMMANDS.values():
        aliases_display = ", ".join(cmd_info.get("aliases", []))
        commands_table.add_row(aliases_display, cmd_info.get("description", ""))

    art_text = Text(welcome_art, style="accent.bold", justify="center")

    commands_panel = Group(
        art_text,
        # Rule(style="accent"),
        Text("Quick Controls\n", style="title"),
        commands_table,
    )

    console.print(
        Panel(
            # Columns([art_text, commands_panel], expand=True, equal=True),
            commands_panel,
            title=f"Version: {ui_config.Version}",
            title_align="right",
            padding=(1, 2),
            box=box.ROUNDED,
            border_style="accent",
        ),
        justify="center",
    )


def select_hierarchy_mode(*args):
    """
    Prompt user to select hierarchy mode.
    """
    console.print("[title]\nChoose your preferred interaction mode:[/title]")
    console.print(
        "1. [accent]Collaborative[/accent] - Agents can handoff directly to each other [dim](default)[/dim]"
    )
    console.print(
        "2. [accent]Managerial[/accent] - Triage agent manages all interactions behind the scenes"
    )
    console.print()

    ui_config.SKIP_TURN = True

    while True:
        mode_choice = IntPrompt.ask("Mode", choices=["1", "2"], default="1")
        if mode_choice == "1":
            ui_config.HEIRARCHY_MODE = "collaborative"
            console.print("[accent.bold]Collaborative mode[/accent.bold]")
            break
        else:
            ui_config.HEIRARCHY_MODE = "managerial"
            console.print("[accent.bold]Managerial mode[/accent.bold]")
            break


def select_interaction_mode(*args):
    """
    Prompt user to select interaction mode.
    """
    console.print("[title]\nChoose your preferred interaction mode:[/title]")
    console.print("1. [accent]Text[/accent] [dim](default)[/dim]")
    console.print("2. [accent]Voice[/accent] - STT (Whisper) + TTS (Piper)")
    console.print()

    ui_config.SKIP_TURN = True

    while True:
        mode_choice = IntPrompt.ask("Mode", choices=["1", "2"], default=1)
        if mode_choice == 1:
            ui_config.INTERACTION_MODE = "text"
            console.print("[accent.bold]Text mode[/accent.bold]")
            break
        else:
            setup_voice_mode()
            ui_config.INTERACTION_MODE = "voice"
            console.print("[accent.bold]Voice mode[/accent.bold]")
            break


def select_context_agent_mode(*args):
    """
    Prompt user to select whether to use context agent for memory.
    """
    console.print(
        "[title]\nChoose if you want to use context agent for memory:[/title]"
    )
    console.print("1. [accent]Yes[/accent] - Use context agent for memory")
    console.print("2. [accent]No[/accent] [dim](default)[/dim]")
    console.print()

    ui_config.SKIP_TURN = True

    while True:
        mode_choice = IntPrompt.ask("Mode", choices=["1", "2"], default="2")
        if mode_choice == 1:
            ui_config.USE_CONTEXT_MANAGER = True
            console.print("[accent.bold]Using context agent for memory[/accent.bold]")
            break
        else:
            ui_config.USE_CONTEXT_MANAGER = False
            console.print(
                "[accent.bold]Not using context agent for memory[/accent.bold]"
            )
            break


def handle_agents(user_msg: str) -> None:
    """
    Handle `/agent` command for listing and switching agents.
    """

    global CURRENT_AGENT

    ui_config.SKIP_TURN = True

    parts = user_msg.split()
    agents_table = Table(
        title="Available Agents",
        show_header=True,
        header_style="title",
        expand=True,
        box=box.ROUNDED,
        padding=(0, 1),
    )
    agents_table.add_column("Key", style="accent.bold")
    agents_table.add_column("Agent", style="assistant")

    if len(parts) == 1:
        agents_panel = Text()
        agents_panel.append("\n")
        for key, value in AGENTS_REGISTRY.items():
            agents_panel.append(
                f"  {key}: {str(value.name).capitalize()}\n", style="white"
            )
            agents_table.add_row(key, str(value.name).capitalize())
        agents_panel.append(
            "\nUse /agents <name> OR /a <name> to talk to a specific agent.\n",
            style="accent.bold",
        )
        console.print(
            Group(
                agents_table,
                Text(
                    "Use /agents <key> OR /a <key> to talk to a specific agent.",
                    style="title",
                ),
            ),
            justify="center",
        )

    elif len(parts) == 2:
        agent_name = parts[1].lower()
        if agent_name in AGENTS_REGISTRY:
            CURRENT_AGENT = AGENTS_REGISTRY[agent_name]
            console.print(
                f"[dim]Switched to {str(CURRENT_AGENT.name).capitalize()}[/dim]"
            )
        else:
            console.print(f"[error]Unknown agent: {agent_name}[/error]")

    else:
        console.print("[warning]Usage: /agents or /a <name>[/warning]")


# Display conversation history
def display_history(*args):
    """
    Display the conversation history.
    """

    ui_config.SKIP_TURN = True

    if not ui_config.CONVERSATION_HISTORY:
        console.print("[dim]No conversation history available.[/dim]")
        return

    output_lines = []

    for entry in ui_config.CONVERSATION_HISTORY:
        role = entry.get("role", "") or entry.get("type", "unknown")
        role = str(role)
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
                    f"# {role.capitalize()}\n\n```json\n{json.dumps(content, indent=2)}\n```\n\n"
                )
        else:
            # Handle function calls
            if "name" in entry:
                name: str = entry["name"]
                if entry["name"].startswith("transfer_"):
                    name = name.replace("_", " ").capitalize()
                    output_lines.append(f"# Tool Call\n\n`{name}`\n\n")
                    continue
                output_lines.append(f"# Tool Call\n\n`{name}`\n\n")
                if "arguments" in entry:
                    args = (
                        json.loads(entry["arguments"])
                        if isinstance(entry["arguments"], str)
                        else entry["arguments"]
                    )
                    output_lines.append(
                        f"**Arguments:**\n\n```json\n{json.dumps(args, indent=2)}\n```\n\n"
                    )
            if "output" in entry:
                output = entry["output"]
                output = str(output)
                if output.startswith('{"'):
                    continue
                output_lines.append(f"# Tool Output\n\n```markdown\n{output}\n```\n")

    history_text = "\n".join(output_lines)

    console.print(
        Panel(
            Markdown(history_text, style="assistant"),
            title=Text("Conversation History", style="title"),
            border_style="accent",
            highlight=True,
            width=CONSOLE_WIDTH,
            padding=(1, 1),
        ),
        justify="center",
    )


# Help panel
def help_panel(*args):
    """
    Display available commands.
    """
    ui_config.SKIP_TURN = True
    help_table = Table(
        title="Slash Commands",
        show_header=True,
        header_style="title",
        expand=True,
        box=box.ROUNDED,
        padding=(0, 1),
    )
    help_table.add_column("Command", style="accent.bold")
    help_table.add_column("Description", style="assistant")

    for cmd_info in COMMANDS.values():
        alias_str = ", ".join(cmd_info["aliases"])
        help_table.add_row(alias_str, cmd_info["description"])

    console.print(help_table, justify="center")


# Quit application
def quit_session(*args):
    ui_config.QUIT_SESSION = True


# Clear conversation
def clear_console(*args):
    ui_config.SKIP_TURN = True
    console.clear()
    current_display = str(CURRENT_AGENT.name).capitalize()
    console.print(f"[dim]Current agent: {current_display}[/dim]")


# Clear conversation history
def clear_history(*args):
    ui_config.SKIP_TURN = True
    ui_config.CONVERSATION_HISTORY.clear()
    console.clear()
    current_display = str(CURRENT_AGENT.name).capitalize()
    console.print(f"[dim]Current agent: {current_display}[/dim]")


def print_usage(usage: Usage) -> None:
    usage_string = ""
    usage_string += "\n=== Usage ===\n"
    usage_string += f"Input tokens: {usage.input_tokens}\n"
    usage_string += f"Output tokens: {usage.output_tokens}\n"
    usage_string += f"Total tokens: {usage.total_tokens}\n"
    usage_string += f"Requests: {usage.requests}\n"
    for i, request in enumerate(usage.request_usage_entries):
        usage_string += (
            f"  {i + 1}: {request.input_tokens} input, {request.output_tokens} output\n"
        )
    console.print(
        usage_string, style="dim", justify="center", highlight=True, crop=True
    )


# Command registry
COMMANDS = {
    "help": {
        "aliases": ["/help", "/h"],
        "description": "Show this help message",
        "handler": help_panel,
    },
    "history": {
        "aliases": ["/history", "/hs"],
        "description": "Show conversation history",
        "handler": display_history,
    },
    "agents": {
        "aliases": ["/agents", "/a"],
        "description": "List and switch agents",
        "handler": handle_agents,
    },
    "hierarchy": {
        "aliases": ["/hierarchy", "/hmode"],
        "description": "Change hierarchy mode",
        "handler": select_hierarchy_mode,
    },
    "interaction": {
        "aliases": ["/interaction", "/imode"],
        "description": "Change interaction mode",
        "handler": select_interaction_mode,
    },
    "context": {
        "aliases": ["/context", "/ctx"],
        "description": "Toggle context agent for memory",
        "handler": select_context_agent_mode,
    },
    "clear": {
        "aliases": ["/clear", "/c"],
        "description": "Clear screen",
        "handler": clear_console,
    },
    "clear_history": {
        "aliases": ["/clear_history", "/ch"],
        "description": "Clear conversation history",
        "handler": clear_history,
    },
    "quit": {
        "aliases": ["/quit", "/exit", "/q"],
        "description": "Exit the application",
        "handler": quit_session,
    },
}


# Handle slash commands
def slash_commands(user_msg: str) -> None:
    """
    Handle special commands like quit and clear.
    """
    for cmd_info in COMMANDS.values():
        if user_msg.lower().split()[0] in [a.lower() for a in cmd_info["aliases"]]:
            cmd_info["handler"](user_msg)


# Stream agent response with rich live updates
async def stream_agent_response() -> RunResultStreaming:
    """
    Stream the agent's response and handle events.

    :param agent: The current agent
    :param inputs: List of input messages
    :param hierarchy_mode: The current hierarchy mode
    :return: Updated agent and run result
    """

    global CURRENT_AGENT

    result = Runner.run_streamed(
        starting_agent=CURRENT_AGENT,
        input=ui_config.CONVERSATION_HISTORY,
        max_turns=MAX_TURNS,
        run_config=RunConfig(nest_handoff_history=False),
    )

    # Create a live display for streaming response
    full_response: str = ""
    events: list = []
    thinking_text: str = ""
    thinking = False

    with Live(
        Group(
            Panel(
                Group(*events),
                title="Events",
                title_align="left",
                style="dim",
                padding=(0, 1),
            ),
            Panel(
                Markdown(full_response, style="assistant"),
                title=Text(f"{str(CURRENT_AGENT.name).capitalize()}", style="title"),
                title_align="left",
                border_style="accent",
                padding=(1, 1),
            ),
        ),
        console=console,
        refresh_per_second=1,
    ) as live:

        try:
            # Stream the response
            async for event in result.stream_events():
                # print("\n---\n")
                # print(event)
                # print(type(event))
                # print("\n---\n")

                # Handle the streamed text output
                if isinstance(event, RawResponsesStreamEvent):
                    data = event.data

                    if isinstance(data, ResponseTextDeltaEvent):
                        delta = data.delta

                        if any([tag in delta for tag in ["<think>", "[THINK]"]]):
                            delta = delta.replace("<think>", "").replace("[THINK]", "")
                            thinking = True
                        elif any([tag in delta for tag in ["</think>", "[/THINK]"]]):
                            delta = delta.replace("</think>", "").replace(
                                "[/THINK]", ""
                            )
                            thinking_text += delta
                            thinking = False
                            if thinking_text.strip():
                                events.append(
                                    Panel(
                                        thinking_text.strip(),
                                        title="Reasoning",
                                        style="dim",
                                        padding=(0, 1),
                                    )
                                )
                            thinking_text = ""
                        if thinking:
                            thinking_text += delta
                        else:
                            full_response += delta

                    elif isinstance(data, ResponseReasoningTextDeltaEvent):
                        delta = data.delta
                        thinking_text += delta

                    elif isinstance(data, ResponseReasoningSummaryTextDeltaEvent):
                        delta = data.delta
                        thinking_text += delta

                # Handle tool calls and handoffs
                elif isinstance(event, RunItemStreamEvent):

                    # Handle handoff
                    ###############
                    # This here decides if you actually want to handoff to a new agent or let the orchestrator talk to it behind the scenes and return to you with the result.
                    ###############
                    if (
                        event.name == "handoff_occured"
                    ):  # Note: This is misspelled in the library

                        target_name = event.item.target_agent.name  # type: ignore
                        display_target = str(target_name).capitalize()

                        if ui_config.HEIRARCHY_MODE == "collaborative":
                            # Switch to the new agent for direct handoff
                            CURRENT_AGENT = event.item.target_agent  # type: ignore
                            handoff_msg = f"Handed-off to {display_target}."
                        else:
                            # Managerial mode: keep current agent, just notify
                            handoff_msg = f"Delegated to {display_target}."
                        events.append(
                            Panel(
                                handoff_msg,
                                title="Handoff",
                                style="dim",
                                padding=(0, 1),
                            )
                        )

                    # Handle tool calls
                    elif event.name == "tool_called":
                        tool_name: str = getattr(
                            event.item.raw_item, "name", "unknown tool"
                        )
                        if tool_name.startswith("transfer_"):
                            tool_msg = tool_name.replace("_", " ").split()[2:]
                            tool_msg = [i.capitalize() for i in tool_msg]
                            tool_msg = " ".join(tool_msg)
                            continue
                        else:
                            tool_msg = f"`{tool_name}`"
                        tool_args = getattr(event.item.raw_item, "arguments", "")
                        if tool_args and tool_args != "{}":
                            tool_msg += f"\n\nArgs: {json.dumps(json.loads(tool_args), indent=2)}"
                        events.append(
                            Panel(
                                tool_msg,
                                title="Tool Call",
                                style="dim",
                                padding=(0, 1),
                            )
                        )

                    # Handle tool outputs
                    elif event.name == "tool_output":
                        tool_output = str(event.item.output).strip()  # type: ignore
                        if tool_output:
                            tool_output = f"Tool output: {tool_output}"
                            # events.append(Panel(tool_output, style="dim", padding=(0, 1)))

                if thinking_text.strip():
                    if len(thinking_text) > 2500:
                        thinking_text = "..." + thinking_text[-2500:]
                    thinking_panel = Panel(
                        thinking_text,
                        title="Reasoning",
                        style="dim",
                        padding=(0, 1),
                    )
                    events_panel = Panel(
                        Group(*events[-1:], thinking_panel),
                        title="Events",
                        title_align="left",
                        style="dim",
                        border_style="border",
                        padding=(0, 1),
                    )
                else:
                    events_panel = Panel(
                        Group(*events[-4:]),
                        title="Events",
                        title_align="left",
                        style="dim",
                        border_style="border",
                        padding=(0, 1),
                    )

                display = Group(
                    events_panel,
                    Panel(
                        Markdown(full_response, style="assistant"),
                        title=Text(
                            f"{str(CURRENT_AGENT.name).capitalize()}",
                            style="title",
                        ),
                        title_align="left",
                        border_style="accent",
                        padding=(1, 1),
                    ),
                )

                # Update the live display
                live.update(
                    display,
                    refresh=True,
                )

        except KeyboardInterrupt:
            console.print("\n[error]Interrupted by user[/error]")
        except Exception as e:
            console.print(f"[error]Error: {e}[/error]")

        # TODO: remove reasoning from messages
        history = result.to_input_list()
        for item in history:
            content = item.get("content", "")
            if isinstance(content, str):
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
                item["content"] = content  # type: ignore
            elif isinstance(content, list):
                text = content[0].get("text", "")
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
                item["content"][0]["text"] = text  # type:ignore

        ui_config.CONVERSATION_HISTORY = history

        full_response = re.sub(
            r"<think>.*?</think>", "", full_response, flags=re.DOTALL
        )
        result.final_output = full_response.strip()

    # print_usage(result.context_wrapper.usage)

    return result


# Main CLI loop
async def run_cli():
    """
    Main conversation loop

    :param agents: Dict of available agents
    :param starting_agent: The agent to start the conversation with
    """

    global CURRENT_AGENT
    session_context: str = ""

    try:
        select_hierarchy_mode()
        select_interaction_mode()
        select_context_agent_mode()
        console.print("\n\n")
        ui_config.SKIP_TURN = False
    except Exception as e:
        raise Exception(f"Error selecting modes")

    welcome_panel()
    ui_config.CONVERSATION_HISTORY.clear()

    while True:

        if ui_config.QUIT_SESSION:
            if tts_client:
                tts_client.shutdown()
            if stt_client:
                stt_client.shutdown()
            break

        if session_context and ui_config.USE_CONTEXT_MANAGER:
            ui_config.CONVERSATION_HISTORY = [
                {"content": session_context, "role": "assistant"}
            ]

        if ui_config.INTERACTION_MODE == "text":

            try:
                user_msg = Prompt.ask("\n[dim]You[/dim]")

                if not user_msg:
                    continue

                if user_msg.startswith("<ml>"):
                    while not user_msg.strip().endswith("</ml>"):
                        next_line = Prompt.ask(":")
                        user_msg += "\n" + next_line
                        user_msg = user_msg.strip()
                    user_msg = user_msg.replace("<ml>", "").replace("</ml>", "").strip()

                # Handle special commands
                slash_commands(user_msg.lower())

                if ui_config.SKIP_TURN:
                    ui_config.SKIP_TURN = False
                    continue

                if ui_config.QUIT_SESSION:
                    if tts_client:
                        tts_client.shutdown()
                    if stt_client:
                        stt_client.shutdown()
                    break
            except Exception as e:
                console.print(f"[error]Input Error: {e}[/error]")
                continue

        else:

            setup_voice_mode()

            try:
                user_msg = stt_client.text()  # type: ignore
                console.print(f"\n[user]You:[/user] {user_msg}\n")
            except Exception as e:
                console.print(f"[error]STT Error: {e}[/error]")
                ui_config.INTERACTION_MODE = "text"
                continue

            if not user_msg:
                console.print(
                    "[warning]No speech detected. Please try again.[/warning]"
                )
                continue

        ui_config.SKIP_TURN = False
        ui_config.CONVERSATION_HISTORY.append({"content": user_msg, "role": "user"})

        if ui_config.USE_CONTEXT_MANAGER:

            try:
                temp = CURRENT_AGENT
                CURRENT_AGENT = context_agent.agent
                context_result = await stream_agent_response()
                CURRENT_AGENT = temp
            except KeyboardInterrupt:
                console.print("\n[error]Interrupted by user[/error]")
                continue

            if context_result.final_output != session_context:
                session_context = str(context_result.final_output).strip()
                console.print(f"[dim]Context updated.[/dim]")

            if session_context:
                ui_config.CONVERSATION_HISTORY = [
                    {"role": "assistant", "content": session_context},
                    {"role": "user", "content": user_msg},
                ]

        # Stream the response
        try:
            result = await stream_agent_response()
        except KeyboardInterrupt:
            console.print("\n[error]Interrupted by user[/error]")
            continue

        if ui_config.INTERACTION_MODE == "voice":
            if tts_client and result.final_output:
                tts_client.speak(str(result.final_output))

        # ui_config.CONVERSATION_HISTORY = result.to_input_list()

        if ui_config.USE_CONTEXT_MANAGER:
            for input_item in ui_config.CONVERSATION_HISTORY:
                if input_item.get("type") in ["function_call", "function_call_output"]:

                    try:
                        temp = CURRENT_AGENT
                        CURRENT_AGENT = context_agent.agent
                        context_result = await stream_agent_response()
                        CURRENT_AGENT = temp
                    except KeyboardInterrupt:
                        console.print("\n[error]Interrupted by user[/error]")
                        continue

                    if context_result.final_output:
                        session_context = str(context_result.final_output).strip()
                        console.print(f"[dim]Context updated.[/dim]")
                    break
