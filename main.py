import asyncio
from typing import List

import asyncio

from openai.types.responses import ResponseContentPartDoneEvent, ResponseTextDeltaEvent
from agents import (
    RawResponsesStreamEvent,
    Runner,
    RunItemStreamEvent,
    TResponseInputItem,
    set_tracing_disabled,
)


"""
Multi-Agent System with Web Search and Filesystem capabilities.
Features:
- Triage agent for routing requests
- Web search agent for internet searches
- Filesystem agent for file operations within sandbox
- Secure sandboxed file operations
"""


set_tracing_disabled(disabled=True)


# Agent Definitions
from my_agents.ideation_agent import create_ideation_agent
from my_agents.web_search_agent import create_web_search_agent
from my_agents.filesystem_agent import create_filesystem_agent
from my_agents.triage_agent import create_triage_agent

# Create agents
ideation_agent = create_ideation_agent()

web_search_agent = create_web_search_agent()

filesystem_agent = create_filesystem_agent()

triage_agent = create_triage_agent(
    handoffs=[ideation_agent, web_search_agent, filesystem_agent]
)


# CLI Interface
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.live import Live


console = Console()
console.clear()


def welcome_panel():
    """
    Create a welcome panel.
    """
    welcome_text = Text()
    welcome_text.append("🤖 Multi-Agent Assistant Ready!\n\n", style="bold yellow")
    welcome_text.append("I can help you with:\n", style="bold yellow")
    welcome_text.append("  💡 Brainstorming and ideation\n", style="bold white")
    welcome_text.append("  🔍 Web searches\n", style="bold white")
    welcome_text.append("  📁 File operations\n", style="bold white")
    welcome_text.append("\nType 'quit' to exit", style="dim")

    console.print(
        Panel(
            welcome_text,
            title="Multi-Agent System",
            subtitle="Version 1.0.0",
            border_style="yellow",
            highlight=True,
        )
    )


async def main():
    """Main conversation loop"""

    welcome_panel()

    # Get initial user input
    console.print("\n[bold yellow]👋 How can I help you today?[/bold yellow]")

    agent = triage_agent
    inputs: List[TResponseInputItem] = []

    while True:

        user_msg = console.input("\n[cyan]>[/cyan] ")

        if user_msg.lower() in ["quit", "exit", "/q", "/quit", "/bye", "/exit"]:
            console.clear()
            console.print("[bold green]👋 Goodbye![/bold green]")
            break

        if user_msg.lower() in ["/clear"]:
            inputs = []
            console.clear()
            console.print("[bold yellow]🔄 Conversation cleared![/bold yellow]")
            welcome_panel()
            continue

        inputs.append({"content": user_msg, "role": "user"})

        # Each conversation turn is traced
        result = Runner.run_streamed(
            starting_agent=agent,
            input=inputs,
        )

        # agent = result.current_agent

        # Create a live display for streaming response
        response_text = Text()
        events_text = Text(style="dim")
        with Live(
            Group(
                Panel(events_text, title="Events", border_style="dim"),
                Panel(response_text, title=f"🤖 {agent.name}", border_style="yellow"),
            ),
            console=console,
            refresh_per_second=10,
        ) as live:
            # Stream the response
            async for event in result.stream_events():
                if isinstance(event, RawResponsesStreamEvent):
                    data = event.data
                    if isinstance(data, ResponseTextDeltaEvent):
                        response_text.append(data.delta)
                        live.update(
                            Group(
                                Panel(events_text, title="Events", border_style="dim"),
                                Panel(
                                    response_text,
                                    title=f"🤖 {agent.name}",
                                    border_style="yellow",
                                ),
                            )
                        )
                    elif isinstance(data, ResponseContentPartDoneEvent):
                        pass
                elif isinstance(event, RunItemStreamEvent):
                    # Handle handoffs and tool calls
                    if event.name == "handoff_requested":
                        handoff_msg = f"\n🔄 Handoff requested to {event.item.raw_item.name if hasattr(event.item.raw_item, 'name') else 'another agent'}.\n"
                        events_text.append(handoff_msg)
                    elif (
                        event.name == "handoff_occured"
                    ):  # Note: This is misspelled in the library
                        handoff_msg = f"\n✅ Handoff completed to {event.item.target_agent.name}.\n"
                        events_text.append(handoff_msg)
                    elif event.name == "tool_called":
                        tool_name = getattr(event.item.raw_item, "name", "unknown tool")
                        tool_args = getattr(event.item.raw_item, "arguments", {})
                        tool_msg = f"🛠️ Tool called: {tool_name}"
                        if tool_args:
                            tool_msg += f" with args: {tool_args}"
                        tool_msg += "\n"
                        events_text.append(tool_msg)
                    elif event.name == "tool_output":
                        tool_output = getattr(
                            event.item.raw_item, "content", "No output"
                        )
                        tool_output_msg = f"\n📤 Tool output: {tool_output}\n"
                        events_text.append(tool_output_msg)
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
                                response_text,
                                title=f"🤖 {agent.name}",
                                border_style="yellow",
                            ),
                        )
                    )

        # Update conversation state
        inputs = result.to_input_list()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]👋 System shutdown by user[/bold yellow]")
    except Exception as e:
        console.print(f"\n[bold red]❌ System error: {e}[/bold red]")
