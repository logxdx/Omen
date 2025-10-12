from typing import List
import json

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
from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .art import get_random_omen
from config.agent_config import Version, MAX_TURNS
from tts.kokoro import KokoroTTS as TTS
from my_agents import context_agent, memory_agent


set_tracing_disabled(disabled=True)


CONSOLE_WIDTH = 120
console = Console(color_system="truecolor", width=CONSOLE_WIDTH)
console.clear()

MESSAGE_HISTORY: list[TResponseInputItem] = []

welcome_art = get_random_omen()
_tts = None


def get_tts():
    global _tts
    if _tts is None:
        _tts = TTS()
    return _tts


def welcome_panel():
    """
    Welcome Panel
    """
    console.clear()

    commands_table = Table.grid(padding=(0, 4))
    commands_table.add_column(style="bold purple", justify="right")
    commands_table.add_column(style="white", justify="left")

    for cmd_info in COMMANDS.values():
        aliases_display = ", ".join(cmd_info.get("aliases", []))
        commands_table.add_row(aliases_display, cmd_info.get("description", ""))
    commands_table.add_row("Ctrl + X", "Interrupt a streaming reply")

    art_text = Text(welcome_art, style="bold purple", justify="center")

    commands_panel = Group(
        Text("Quick Controls", style="bold white"),
        Rule(style="purple"),
        commands_table,
    )

    console.print(
        Panel(
            Columns([art_text, commands_panel], expand=True, equal=True),
            title=f"Version: {Version}",
            title_align="right",
            padding=(1, 2),
            box=box.ROUNDED,
            border_style="purple",
        ),
        justify="center",
    )


def select_hierarchy_mode():
    """
    Prompt user to select hierarchy mode.
    """
    console.print("[bold white]\nChoose your preferred interaction mode:[/bold white]")
    console.print(
        "1. [purple]Managerial[/purple] - Triage agent manages all interactions behind the scenes [bold dim](default)[/bold dim]"
    )
    console.print(
        "2. [purple]Collaborative[/purple] - Agents can handoff directly to each other"
    )
    console.print()

    while True:
        mode_choice = IntPrompt.ask("Mode", choices=["1", "2"], default="1")
        if mode_choice == "1":
            hierarchy_mode = "managerial"
            console.print("[bold purple]Managerial mode[/bold purple]")
            break
        else:
            hierarchy_mode = "collaborative"
            console.print("[bold purple]Collaborative mode[/bold purple]")
            break
    return hierarchy_mode


def select_interaction_mode():
    """
    Prompt user to select interaction mode.
    """
    console.print("[bold white]\nChoose your preferred interaction mode:[/bold white]")
    console.print("1. [purple]Text[/purple] [bold dim](default)[/bold dim]")
    console.print("2. [purple]Voice[/purple] - STT (Whisper) + TTS (Piper)")
    console.print()

    while True:
        mode_choice = IntPrompt.ask("Mode", choices=["1", "2"], default="1")
        if mode_choice == "1":
            interaction_mode = "text"
            console.print("[bold purple]Text mode[/bold purple]")
            break
        else:
            interaction_mode = "voice"
            console.print("[bold purple]Voice mode[/bold purple]")
            break
    return interaction_mode


def handle_agents_command(user_msg: str, agents: dict, agent: Agent) -> Agent:
    """
    Handle `/agent` command for listing and switching agents.
    """
    parts = user_msg.split()
    agents_table = Table(
        title="Available Agents",
        show_header=True,
        header_style="bold white",
        expand=True,
        box=box.ROUNDED,
        padding=(0, 1),
    )
    agents_table.add_column("Key", style="bold purple")
    agents_table.add_column("Agent", style="white")

    if len(parts) == 1:
        agents_panel = Text()
        agents_panel.append("\n")
        for key, value in agents.items():
            agents_panel.append(
                f"  {key}: {str(value.name).capitalize()}\n", style="white"
            )
            agents_table.add_row(key, str(value.name).capitalize())
        agents_panel.append(
            "\nUse /agents <name> OR /a <name> to talk to a specific agent.\n",
            style="bold purple",
        )
        console.print(
            Group(
                agents_table,
                Text(
                    "Use /agents <key> OR /a <key> to talk to a specific agent.",
                    style="bold white",
                ),
            ),
            justify="center",
        )

    elif len(parts) == 2:
        agent_name = parts[1].lower()
        if agent_name in agents:
            agent = agents[agent_name]
            console.print(
                f"[bold dim]Switched to {str(agent.name).capitalize()}[/bold dim]"
            )
            return agent
        else:
            console.print(f"[bold red]Unknown agent: {agent_name}[/bold red]")

    else:
        console.print("[bold red]Usage: /agents or /a <name>[/bold red]")

    return agent


# Display conversation history
def display_history(inputs: List[TResponseInputItem]):
    """
    Display the conversation history.
    """
    if not inputs:
        console.print("[bold dim]No conversation history available.[/bold dim]")
        return

    output_lines = []

    for entry in inputs:
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
                output_lines.append(f"**Output:**\n```\n{output}\n```\n")

    history_text = "\n".join(output_lines)

    console.print(
        Panel(
            Markdown(history_text, style="white"),
            title=Text("Conversation History", style="bold white"),
            border_style="blue",
            highlight=True,
            width=CONSOLE_WIDTH,
            padding=(1, 1),
        ),
        justify="center",
    )


# Help panel
def help_panel():
    """
    Display available commands.
    """
    help_table = Table(
        title="Slash Commands",
        show_header=True,
        header_style="bold white",
        expand=True,
        box=box.ROUNDED,
        padding=(0, 1),
    )
    help_table.add_column("Command", style="bold purple")
    help_table.add_column("Description", style="white")

    for cmd_info in COMMANDS.values():
        alias_str = ", ".join(cmd_info["aliases"])
        help_table.add_row(alias_str, cmd_info["description"])

    console.print(
        Group(
            help_table,
            Text("Use Ctrl+X to interrupt responses", style="purple"),
        ),
        justify="center",
    )


# Quit application
def handle_quit(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    return True, True, inputs, agent, agents, hierarchy_mode, interaction_mode


# Clear conversation
def handle_clear(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    console.clear()
    current_display = str(agent.name).capitalize()
    console.print(f"[dim]Current agent: {current_display}[/dim]")
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


# Show conversation history
def handle_history(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    display_history(inputs)
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


# Change hierarchy mode
def handle_hierarchy(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    hierarchy_mode = select_hierarchy_mode()
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


# Show help panel
def handle_help(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    help_panel()
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


# Clear conversation history
def handle_clear_history(
    user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode
):
    inputs.clear()
    console.clear()
    console.print("[bold purple]🔄 Conversation history cleared![/bold purple]\n\n")
    current_display = str(agent.name).capitalize()
    console.print(f"[dim]Current agent: {current_display}[/dim]")
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


# List and switch agents
def handle_agents(user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode):
    agent = handle_agents_command(user_msg, agents, agent)
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


# Change interaction mode
def handle_interaction(
    user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode
):
    interaction_mode = select_interaction_mode()
    return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode


# Command registry
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


# Handle slash commands
def slash_commands(
    user_msg: str,
    inputs: list[TResponseInputItem],
    agent: Agent,
    agents: dict,
    hierarchy_mode: str,
    interaction_mode: str,
) -> tuple[bool, bool, list[TResponseInputItem], Agent, dict, str, str]:
    """
    Handle special commands like quit and clear.
    """
    for cmd_info in COMMANDS.values():
        if user_msg.lower().split()[0] in [a.lower() for a in cmd_info["aliases"]]:
            return cmd_info["handler"](
                user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode
            )
    return False, False, inputs, agent, agents, hierarchy_mode, interaction_mode


# Stream agent response with rich live updates
async def stream_agent_response(
    agent: Agent, inputs: list[TResponseInputItem], hierarchy_mode: str
) -> tuple[Agent, RunResultStreaming]:
    """
    Stream the agent's response and handle events.

    :param agent: The current agent
    :param inputs: List of input messages
    :param hierarchy_mode: The current hierarchy mode
    :return: Updated agent and run result
    """
    result = Runner.run_streamed(
        starting_agent=agent, input=inputs, max_turns=MAX_TURNS
    )

    # Create a live display for streaming response
    full_response: str = ""
    markdown_obj = Markdown(full_response, style="bold white")
    events = []
    thinking_text: str = ""

    try:
        with Live(
            Group(
                Panel(
                    Group(*events),
                    title="Events",
                    style="dim",
                    padding=(0, 1),
                ),
                Panel(
                    markdown_obj,
                    title=Text(f"{str(agent.name).capitalize()}", style="bold white"),
                    border_style="purple",
                    padding=(1, 1),
                ),
            ),
            console=console,
            refresh_per_second=1,
        ) as live:

            is_complete = False
            thinking = False
            while not is_complete:

                # Stream the response
                async for event in result.stream_events():

                    # Handle the streamed text output
                    if isinstance(event, RawResponsesStreamEvent):
                        data = event.data

                        if isinstance(data, ResponseTextDeltaEvent):
                            delta = data.delta

                            if "<think>" in delta:
                                thinking = True
                            elif "</think>" in delta:
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
                                thinking_text += delta.replace("<think>", "")
                            else:
                                full_response += delta
                                markdown_obj = Markdown(
                                    full_response, style="bold white"
                                )

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

                            if hierarchy_mode == "collaborative":
                                # Switch to the new agent for direct handoff
                                agent = event.item.target_agent  # type: ignore
                                handoff_msg = f"Handed-off to {display_target}."
                            else:
                                # Managerial mode: keep current agent, just notify
                                handoff_msg = f"Delegated to {display_target}."
                            # events.append(
                            #     Panel(handoff_msg, style="dim", padding=(0, 1))
                            # )

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

                    # Handle agent switch events
                    elif isinstance(event, AgentUpdatedStreamEvent):
                        continue
                        new_agent = event.new_agent
                        if new_agent.name != agent.name:
                            # Already handled in RunItemStreamEvent
                            # agent = new_agent
                            switch_msg = (
                                f"\n🔄 Switched to {str(agent.name).capitalize()}\n"
                            )
                            events_text.append(switch_msg)

                    events = events[-5:]

                    if thinking_text.strip():
                        thinking_panel = Panel(
                            thinking_text,
                            title="Reasoning",
                            style="dim",
                            padding=(0, 1),
                        )
                        events_panel = Panel(
                            Group(*events, thinking_panel),
                            title="Events",
                            style="dim",
                            border_style="white",
                            padding=(0, 1),
                        )
                    else:
                        events_panel = Panel(
                            Group(*events),
                            title="Events",
                            style="dim",
                            border_style="white",
                            padding=(0, 1),
                        )

                    display = Group(
                        events_panel,
                        Panel(
                            markdown_obj,
                            title=Text(
                                f"{str(agent.name).capitalize()}",
                                style="bold white",
                            ),
                            border_style="purple",
                            padding=(1, 1),
                        ),
                    )

                    # Update the live display
                    live.update(
                        display,
                        refresh=True,
                    )

                is_complete = True

    except Exception as e:
        console.print(f"Error: {e}")

    return agent, result


async def agentic_chat():
    pass


async def conversational_chat():
    pass


# Main CLI loop
async def run_cli(
    agents: dict[str, Agent], starting_agent: Agent, use_context_agent=False
):
    """
    Main conversation loop

    :param agents: Dict of available agents
    :param starting_agent: The agent to start the conversation with
    """

    tts_client: TTS = None  # type: ignore
    session_context: str = ""
    try:
        hierarchy_mode = select_hierarchy_mode()
        interaction_mode = select_interaction_mode()
    except Exception as e:
        raise Exception(f"Error selecting modes")
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
    skip: bool = False

    if interaction_mode == "voice":
        if not tts_client:
            tts_client = get_tts()
        try:
            tts_client.speak(str(result.final_output))
        except Exception as e:
            console.print(f"Error: {e}")

    while True:

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
                tts_client.shutdown()
            break
        if skip:
            continue

        inputs.append({"content": user_msg, "role": "user"})

        if use_context_agent:

            # context_result = await Runner.run(
            #     starting_agent=context_agent.agent, input=inputs, max_turns=MAX_TURNS
            # )

            _, context_result = await stream_agent_response(
                memory_agent.agent, inputs, "managerial"
            )

            if context_result.final_output != session_context:
                session_context = str(context_result.final_output).strip()
                console.print(f"[dim]Context updated.[/dim]")

            if session_context:
                inputs = [
                    {"role": "assistant", "content": session_context},
                    {"role": "user", "content": user_msg},
                ]

        # Stream the response
        agent, result = await stream_agent_response(agent, inputs, hierarchy_mode)

        if interaction_mode == "voice":
            if not tts_client:
                tts_client = get_tts()
            try:
                tts_client.speak(str(result.final_output), user_query=user_msg)
            except Exception as e:
                console.print(f"Error: {e}")

        inputs = result.to_input_list()

        if use_context_agent:
            for input_item in inputs:
                if input_item.get("type") in ["function_call", "function_call_output"]:

                    # context_result = await Runner.run(
                    #     starting_agent=context_agent.agent,
                    #     input=inputs,
                    #     max_turns=MAX_TURNS,
                    # )

                    _, context_result = await stream_agent_response(
                        memory_agent.agent, inputs, "managerial"
                    )

                    if context_result.final_output:
                        session_context = str(context_result.final_output).strip()
                        console.print(f"[dim]Context updated.[/dim]")
                    break
