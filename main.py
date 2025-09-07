import asyncio

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

# Add mesh handoffs to all agents
ideation_agent.handoffs.extend([triage_agent, web_search_agent, filesystem_agent])
web_search_agent.handoffs.extend([triage_agent, ideation_agent, filesystem_agent])
filesystem_agent.handoffs.extend([triage_agent, ideation_agent, web_search_agent])

# Agent registry
agents = {
    "triage": triage_agent,
    "web": web_search_agent,
    "fs": filesystem_agent,
    "idea": ideation_agent,
}

display_names = {
    "triage": "Triage Agent",
    "web": "Web Search Agent",
    "fs": "Filesystem Agent",
    "idea": "Ideation Agent",
}


async def main():
    """Main conversation loop"""

    from cli_interface.interface import run_cli

    await run_cli(agents, display_names, triage_agent)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[bold yellow]👋 System shutdown by user[/bold yellow]")
    except Exception as e:
        print(f"\n[bold red]❌ System error: {e}[/bold red]")
