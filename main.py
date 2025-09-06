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
from my_agents.web_search_agent import create_web_search_agent
from my_agents.filesystem_agent import create_filesystem_agent
from my_agents.triage_agent import create_triage_agent

# Create agents
web_search_agent = create_web_search_agent()

filesystem_agent = create_filesystem_agent()

triage_agent = create_triage_agent(handoffs=[web_search_agent, filesystem_agent])


# CLI Interface
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live


console = Console()
console.clear()


async def main():
    """Main conversation loop"""
    # Create a welcome panel
    welcome_text = Text()
    welcome_text.append("🤖 Multi-Agent Assistant Ready!\n\n", style="bold cyan")
    welcome_text.append("I can help you with:\n", style="white")
    welcome_text.append("  🔍 Web searches\n", style="green")
    welcome_text.append("  📁 File operations\n", style="blue")
    welcome_text.append("\nType 'quit' to exit", style="dim")

    console.print(Panel(welcome_text, title="Multi-Agent System", border_style="cyan"))

    # Get initial user input
    console.print("\n[bold yellow]How can I help you today?[/bold yellow]\n")

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
            continue

        inputs.append({"content": user_msg, "role": "user"})

        # Each conversation turn is traced
        result = Runner.run_streamed(
            starting_agent=agent,
            input=inputs,
        )

        agent = result.current_agent

        # Create a live display for streaming response
        response_text = Text()
        with Live(
            Panel(response_text, title=f"🤖 {agent.name}", border_style="blue"),
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
                            Panel(
                                response_text,
                                title=f"🤖 {agent.name}",
                                border_style="blue",
                            )
                        )
                    elif isinstance(data, ResponseContentPartDoneEvent):
                        pass
                elif isinstance(event, RunItemStreamEvent):
                    # Handle handoffs and tool calls
                    if event.name == "handoff_requested":
                        handoff_msg = f"\n🔄 Handoff requested to {event.item.raw_item.name if hasattr(event.item.raw_item, 'name') else 'another agent'}.\n"
                        response_text.append(handoff_msg)
                    elif (
                        event.name == "handoff_occured"
                    ):  # Note: This is misspelled in the library
                        handoff_msg = f"\n✅ Handoff completed to {event.item.target_agent.name}.\n"
                        response_text.append(handoff_msg)
                    elif event.name == "tool_called":
                        tool_name = getattr(event.item.raw_item, "name", "unknown tool")
                        tool_args = getattr(event.item.raw_item, "arguments", {})
                        tool_msg = f"\n🛠️ Tool called: {tool_name}"
                        if tool_args:
                            tool_msg += f" with args: {tool_args}"
                        tool_msg += "\n"
                        response_text.append(tool_msg)
                    elif event.name == "tool_output":
                        tool_output = getattr(
                            event.item.raw_item, "content", "No output"
                        )
                        tool_output_msg = f"\n📤 Tool output: {tool_output}\n\n"
                        response_text.append(tool_output_msg)
                    elif event.name == "reasoning_item_created":
                        reasoning = getattr(
                            event.item.raw_item, "content", "No reasoning"
                        )
                        reasoning_msg = f"\n🤔 Reasoning: {reasoning}\n"
                        response_text.append(reasoning_msg)
                    # Update the live panel after appending
                    live.update(
                        Panel(
                            response_text, title=f"🤖 {agent.name}", border_style="blue"
                        )
                    )

        # Update conversation state
        inputs = result.to_input_list()


if __name__ == "__main__":
    # Create startup info panel
    startup_info = Text()
    startup_info.append("Starting Multi-Agent System...\n\n", style="bold white")

    console.print(
        Panel(startup_info, title="System Configuration", border_style="green")
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]👋 System shutdown by user[/bold yellow]")
    except Exception as e:
        console.print(f"\n[bold red]❌ System error: {e}[/bold red]")
