from typing import List

from openai.types.responses import ResponseContentPartDoneEvent, ResponseTextDeltaEvent
from agents import (
    RawResponsesStreamEvent,
    Runner,
    RunItemStreamEvent,
    TResponseInputItem,
)
from agents import (
    set_tracing_disabled,
)

set_tracing_disabled(disabled=True)


from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.markdown import Markdown


console = Console(width=120)
console.clear()


def welcome_panel():
    """
    Create a welcome panel.
    """
    welcome_text = Text()
    welcome_text.append("🤖 Multi-Agent Assistant Ready!\n\n", style="bold cyan")
    welcome_text.append("I can help you with:\n", style="bold cyan")
    welcome_text.append("  💡 Brainstorming and ideation\n", style="bold white")
    welcome_text.append("  🔍 Web searches\n", style="bold white")
    welcome_text.append("  📁 File operations\n", style="bold white")
    welcome_text.append("\nCommands:\n", style="bold cyan")
    welcome_text.append(
        "  /agents or /a - List and switch agents\n", style="bold white"
    )
    welcome_text.append("  /clear or /c - Clear conversation\n", style="bold white")
    welcome_text.append("\n/quit or /q to exit", style="dim")

    console.print(
        Panel(
            welcome_text,
            title="Multi-Agent System",
            subtitle="Version 1.0.0",
            border_style="bold green",
            highlight=True,
        )
    )


async def run_cli(agents, display_names, starting_agent):
    """Main conversation loop"""

    welcome_panel()

    # Prompt user to choose hierarchy mode
    console.print("\n[bold cyan]Choose your preferred interaction mode:[/bold cyan]")
    console.print(
        "1. [bold green]Collaborative[/bold green] - Agents can handoff directly to each other"
    )
    console.print(
        "2. [bold green]Managerial[/bold green] - Triage agent manages all interactions behind the scenes"
    )
    console.print()

    while True:
        mode_choice = console.input(
            "[cyan]Enter 1 for Collaborative or 2 for Managerial: [/cyan]"
        ).strip()
        if mode_choice == "1":
            hierarchy_mode = "collaborative"
            console.print("[bold green]✅ Collaborative mode selected![/bold green]")
            break
        elif mode_choice == "2":
            hierarchy_mode = "managerial"
            console.print("[bold blue]✅ Managerial mode selected![/bold blue]")
            break
        else:
            console.print(
                "[bold red]❌ Invalid choice. Please enter 1 or 2.[/bold red]"
            )

    agent = starting_agent
    inputs: List[TResponseInputItem] = []

    current_display = display_names.get(agent.name.replace("_agent", ""), agent.name)
    console.print(f"[bold purple]Current agent: {current_display}[/bold purple]")

    # Generate dynamic introduction by running the agent
    inputs = [
        {
            "content": "Introduce yourself very-briefly and ask for the user's needs.",
            "role": "user",
        }
    ]
    intro_result = Runner.run_streamed(starting_agent=agent, input=inputs)
    intro_response = ""

    async for event in intro_result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if isinstance(data, ResponseTextDeltaEvent):
                intro_response += data.delta

    console.print(
        Panel(intro_response, title=f"🤖 {current_display}", border_style="bold purple")
    )

    while True:

        user_msg = console.input("\n[cyan]>[/cyan] ")

        # Handle /agents command
        if user_msg.lower().startswith("/a") or user_msg.lower().startswith("/agents"):
            parts = user_msg.split()
            if len(parts) == 1:
                # List agents
                console.print("[bold cyan]Available Agents:[/bold cyan]")
                for key, name in display_names.items():
                    console.print(f"  {key}: {name}")
                console.print("\nUse /agents <name> to talk to a specific agent.")
                continue
            elif len(parts) == 2:
                agent_name = parts[1].lower()
                if agent_name in agents:
                    agent = agents[agent_name]
                    inputs = []  # Reset conversation for new agent
                    console.print(
                        f"[bold green]Switched to {display_names[agent_name]}[/bold green]"
                    )
                    continue
                else:
                    console.print(f"[bold red]Unknown agent: {agent_name}[/bold red]")
                    continue
            else:
                console.print("[bold red]Usage: /agents or /agents <name>[/bold red]")
                continue

        # Handle quitting
        if user_msg.lower() in ["quit", "exit", "/q", "/quit", "/bye", "/exit"]:
            console.clear()
            console.print("[bold green]👋 Goodbye![/bold green]")
            break

        # Handle clearing screen and history
        if user_msg.lower() in ["/clear", "/c"]:
            inputs = []
            console.clear()
            console.print("[bold yellow]🔄 Conversation cleared![/bold yellow]")
            welcome_panel()
            current_display = display_names.get(
                agent.name.replace("_agent", ""), agent.name
            )
            console.print(
                f"[bold purple]Current agent: {current_display}[/bold purple]"
            )
            continue

        inputs.append({"content": user_msg, "role": "user"})

        # Each conversation turn is traced
        result = Runner.run_streamed(
            starting_agent=agent,
            input=inputs,
        )

        # Create a live display for streaming response
        full_response = ""
        markdown_obj = Markdown("")
        events_text = Text(style="dim")

        try:
            with Live(
                Group(
                    Panel(events_text, title="Events", border_style="dim"),
                    Panel(
                        markdown_obj,
                        title=f"🤖 {display_names.get(agent.name.replace('_agent', ''), agent.name)}",
                        border_style="yellow",
                    ),
                ),
                console=console,
                refresh_per_second=10,
            ) as live:

                # Stream the response
                async for event in result.stream_events():

                    # Handle the streamed text output
                    if isinstance(event, RawResponsesStreamEvent):
                        data = event.data
                        if isinstance(data, ResponseTextDeltaEvent):
                            full_response += data.delta
                            markdown_obj = Markdown(full_response)
                            live.update(
                                Group(
                                    Panel(
                                        events_text, title="Events", border_style="dim"
                                    ),
                                    Panel(
                                        markdown_obj,
                                        title=f"🤖 {display_names.get(agent.name.replace('_agent', ''), agent.name)}",
                                        border_style="yellow",
                                    ),
                                )
                            )
                        elif isinstance(data, ResponseContentPartDoneEvent):
                            pass

                    # Handle tool calls and handoffs
                    elif isinstance(event, RunItemStreamEvent):

                        # Handle handoffs
                        if event.name == "handoff_requested":
                            target_name = (
                                event.item.raw_item.name  # type: ignore
                                if hasattr(event.item.raw_item, "name")
                                else "another agent"
                            )
                            display_target = (
                                display_names.get(
                                    target_name.replace("_agent", ""), target_name
                                )
                                if target_name != "another agent"
                                else target_name
                            )
                            handoff_msg = (
                                f"\n🔄 Handoff requested to {display_target}.\n"
                            )
                            events_text.append(handoff_msg)

                        elif (
                            event.name == "handoff_occured"
                        ):  # Note: This is misspelled in the library

                            """
                            This here decides if you actually want to handoff to a new agent or let the orchestrator talk to it behind the scenes and return to you with the result.
                            """
                            target_name = event.item.target_agent.name  # type: ignore
                            display_target = display_names.get(
                                target_name.replace("_agent", ""), target_name
                            )

                            if hierarchy_mode == "collaborative":
                                # Switch to the new agent for direct handoff
                                agent = event.item.target_agent  # type: ignore
                                handoff_msg = (
                                    f"\n✅ Handoff completed to {display_target}.\n"
                                )
                            else:
                                # Managerial mode: keep current agent, just notify
                                handoff_msg = (
                                    f"\n🔄 Task delegated to {display_target}.\n"
                                )

                            events_text.append(handoff_msg)

                        # Handle tool calls
                        elif event.name == "tool_called":
                            tool_name = getattr(
                                event.item.raw_item, "name", "unknown tool"
                            )
                            tool_args = getattr(event.item.raw_item, "arguments", {})
                            tool_msg = f"\n🛠️ Tool called: {tool_name}"
                            if tool_args:
                                tool_msg += f" with args: {tool_args}"
                            tool_msg += "\n"
                            events_text.append(tool_msg)

                        # Handle tool outputs
                        elif event.name == "tool_output":
                            tool_output = getattr(
                                event.item.raw_item, "content", "No output"
                            )
                            tool_output_msg = f"\n📤 Tool output: {tool_output}\n"
                            events_text.append(tool_output_msg)

                        # Handle reasoning items
                        elif event.name == "reasoning_item_created":
                            reasoning = getattr(
                                event.item.raw_item, "content", "No reasoning"
                            )
                            reasoning_msg = f"\n🤔 Reasoning: {reasoning}\n"
                            events_text.append(reasoning_msg)

                        # Update the live panel after appending
                        live.update(
                            Group(
                                Panel(events_text, title="Events", border_style="dim"),
                                Panel(
                                    markdown_obj,
                                    title=f"🤖 {display_names.get(agent.name.replace('_agent', ''), agent.name)}",
                                    border_style="yellow",
                                ),
                            )
                        )
        except Exception as e:
            console.print(
                f"\n[bold red]❌ Error occurred in {agent.name}: {e}[/bold red]"
            )

        # Update conversation state
        inputs = result.to_input_list()
