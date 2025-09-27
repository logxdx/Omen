from typing import List

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
from config.agent_config import MAX_TURNS

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.markdown import Markdown
from rich.prompt import Prompt
import keyboard
import threading

from tts.tts import TTS

set_tracing_disabled(disabled=True)


CONSOLE_WIDTH = 125
console = Console(width=CONSOLE_WIDTH)
console.clear()

_tts = None


def get_tts():
    global _tts
    if _tts is None:
        _tts = TTS()
    return _tts


def welcome_panel():
    """
    Create a welcome panel.
    """
    console.clear()
    welcome_text = Text()
    welcome_text.append("\n")
    welcome_text.append(
        "🔄 Intelligent routing to specialized agents\n", style="bold white"
    )
    welcome_text.append("\nFeatures:\n", style="bold purple")
    welcome_text.append(
        "🔍 Web searches and information retrieval\n", style="bold white"
    )
    welcome_text.append("📁 File and filesystem management\n", style="bold white")
    welcome_text.append(
        "💡 Brainstorming and ideation with shared sketchpad\n", style="bold white"
    )
    welcome_text.append("🧠 Memory storage and retrieval\n", style="bold white")
    welcome_text.append("📊 Data analysis and code execution\n", style="bold white")
    welcome_text.append("📚 Study guidance and learning support\n", style="bold white")

    console.print(
        Panel(
            welcome_text,
            title=Text("🤖 AI Multi-Agent CLI Interface", style="bold white"),
            subtitle=Text("Version 1.2.0", style="bold white"),
            border_style="purple",
            highlight=True,
            width=CONSOLE_WIDTH,
        ),
        justify="center",
    )


def help_panel():
    """
    Display available commands.
    """
    help_text = Text()
    help_text.append("\n")
    help_text.append("  /help or /h - Show this help message\n", style="white")
    help_text.append("  /agents or /a - List and switch agents\n", style="white")
    help_text.append("  /hmode or /hierarchy - Change hierarchy mode\n", style="white")
    help_text.append(
        "  /imode or /interaction - Change interaction mode\n", style="white"
    )
    help_text.append("  /clear or /c - Clear conversation\n", style="white")
    help_text.append("  /quit or /q - Exit the application\n", style="dim")
    help_text.append("  Use Ctrl+X to interrupt responses\n", style="purple")

    console.print(
        Panel(
            help_text,
            title=Text("Available Commands", style="bold white"),
            border_style="purple",
            highlight=True,
            width=CONSOLE_WIDTH,
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
        mode_choice = Prompt.ask("Mode", choices=["1", "2"], default="1")
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
        mode_choice = Prompt.ask("Mode", choices=["1", "2"], default="1")
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
    if len(parts) == 1:
        agents_panel = Text()
        agents_panel.append("\n")
        for key, value in agents.items():
            agents_panel.append(
                f"  {key}: {str(value.name).capitalize()}\n", style="white"
            )
        agents_panel.append(
            "\nUse /agents <name> OR /a <name> to talk to a specific agent.\n",
            style="bold purple",
        )
        console.print(
            Panel(
                agents_panel,
                title=Text("Available Agents", style="bold white"),
                border_style="purple",
                highlight=True,
                width=CONSOLE_WIDTH,
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


def handle_special_commands(
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
    if user_msg.lower() in ["quit", "exit", "/q", "/quit", "/bye", "/exit"]:
        console.clear()
        console.print("[bold green]👋 Goodbye![/bold green]")
        return True, True, inputs, agent, agents, hierarchy_mode, interaction_mode
    elif user_msg.lower() in ["/clear", "/c"]:
        inputs = []
        console.clear()
        console.print("[bold purple]🔄 Conversation cleared![/bold purple]\n\n")
        welcome_panel()
        current_display = str(agent.name).capitalize()
        console.print(f"[dim]Current agent: {current_display}[/dim]")
        return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode
    elif user_msg.lower() in ["/help", "/h"]:
        help_panel()
        return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode
    elif user_msg.lower() in ["/hierarchy", "/hmode"]:
        hierarchy_mode = select_hierarchy_mode()
        return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode
    elif user_msg.lower().split()[0] in ["/agents", "/a"]:
        agent = handle_agents_command(user_msg, agents, agent)
        return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode
    elif user_msg.lower() in ["/interaction", "/imode"]:
        interaction_mode = select_interaction_mode()
        return False, True, inputs, agent, agents, hierarchy_mode, interaction_mode
    return False, False, inputs, agent, agents, hierarchy_mode, interaction_mode


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
    full_response = ""
    markdown_obj = Markdown(full_response, style="bold white")
    events_text = Text(style="dim")
    thinking_text = Text("", style="dim")

    # Interrupt handling
    stop_event = threading.Event()

    def interrupt_listener():
        try:
            keyboard.wait("ctrl+x")
            stop_event.set()
        except:
            pass

    interrupt_thread = threading.Thread(target=interrupt_listener, daemon=True)
    interrupt_thread.start()

    try:

        with Live(
            Group(
                Panel(
                    Group(events_text, thinking_text),
                    title="Events",
                    border_style="dim",
                ),
                Panel(
                    markdown_obj,
                    title=Text(
                        f"🤖 {str(agent.name).capitalize()}", style="bold white"
                    ),
                    border_style="yellow",
                ),
            ),
            console=console,
            refresh_per_second=1,
        ) as live:

            # Stream the response
            async for event in result.stream_events():

                # Handle the streamed text output
                if isinstance(event, RawResponsesStreamEvent):
                    data = event.data

                    if isinstance(data, ResponseTextDeltaEvent):
                        delta = data.delta
                        full_response += delta
                        markdown_obj = Markdown(full_response, style="bold white")

                    elif isinstance(data, ResponseReasoningTextDeltaEvent):
                        delta = data.delta
                        thinking_text.append(delta)

                    elif isinstance(data, ResponseReasoningSummaryTextDeltaEvent):
                        delta = data.delta
                        thinking_text.append(delta)

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
                            handoff_msg = f"\n✅ Handed-off to {display_target}.\n"
                        else:
                            # Managerial mode: keep current agent, just notify
                            handoff_msg = f"\n✅ Delegated to {display_target}.\n"

                        events_text.append(handoff_msg)

                    # Handle tool calls
                    elif event.name == "tool_called":
                        tool_name = getattr(event.item.raw_item, "name", "unknown tool")
                        tool_args = getattr(event.item.raw_item, "arguments", {})
                        tool_msg = f"\n⚙️ Tool: {tool_name} |"
                        if tool_args:
                            tool_msg += f" Args: {str(tool_args)[:100]}\n"
                        events_text.append(tool_msg)

                    # Handle tool outputs
                    elif event.name == "tool_output":
                        tool_output = str(event.item.output).strip()  # type: ignore
                        if tool_output:
                            tool_output_msg = f"\n📤 Tool output: {tool_output[:100]}\n"
                            # events_text.append(tool_output_msg)

                # Handle agent switch events
                elif isinstance(event, AgentUpdatedStreamEvent):
                    new_agent = event.new_agent
                    if new_agent.name != agent.name:
                        # Already handled in RunItemStreamEvent
                        pass
                        # agent = new_agent
                        switch_msg = (
                            f"\n🔄 Switched to {str(agent.name).capitalize()}.\n"
                        )
                        events_text.append(switch_msg)

                # Update the live display
                live.update(
                    Group(
                        Panel(
                            Group(events_text, thinking_text),
                            title="Events",
                            border_style="dim",
                        ),
                        Panel(
                            markdown_obj,
                            title=Text(
                                f"🤖 {str(agent.name).capitalize()}", style="bold white"
                            ),
                            border_style="yellow",
                        ),
                    )
                )

                if stop_event.is_set():
                    console.print("\n[bold red]⚠️ Interrupted by user[/bold red]")
                    break

    except Exception as e:
        console.print(f"\n[bold red]❌ Error occurred in {agent.name}: {e}[/bold red]")

    return agent, result


async def run_cli(agents: dict[str, Agent], starting_agent: Agent):
    """
    Main conversation loop

    :param agents: Dict of available agents
    :param starting_agent: The agent to start the conversation with
    """

    tts_client: TTS = None  # type: ignore
    try:
        hierarchy_mode = select_hierarchy_mode()
        interaction_mode = select_interaction_mode()
    except Exception as e:
        raise Exception(f"Error selecting modes")
    if interaction_mode == "voice":
        tts_client = get_tts()
    agent = starting_agent
    handle_special_commands("/c", [], agent, agents, hierarchy_mode, interaction_mode)
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
            speech = tts_client.speak(str(result.final_output))
            console.print(
                Panel(speech, title="Speech", border_style="dim", style="dim")
            )
        except Exception as e:
            console.print(f"\n[bold red]❌ TTS Error: {e}[/bold red]")

    while True:

        user_msg = Prompt.ask("\n[dim]You[/dim]")
        if not user_msg.strip():
            continue

        inputs.append({"content": user_msg, "role": "user"})

        # Handle special commands
        quit_flag, skip, inputs, agent, agents, hierarchy_mode, interaction_mode = (
            handle_special_commands(
                user_msg, inputs, agent, agents, hierarchy_mode, interaction_mode
            )
        )
        if quit_flag:
            if tts_client:
                tts_client.shutdown()
            break
        if (not inputs) or skip:
            continue

        # Stream the response
        agent, result = await stream_agent_response(agent, inputs, hierarchy_mode)

        if interaction_mode == "voice":
            try:
                speech = tts_client.speak(str(result.final_output), user_query=user_msg)
                console.print(
                    Panel(speech, title="Speech", border_style="dim", style="dim")
                )
            except Exception as e:
                console.print(f"\n[bold red]❌ TTS Error: {e}[/bold red]")

        # Update conversation state
        inputs = result.to_input_list()
