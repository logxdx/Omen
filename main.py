import asyncio
# from cli.interface import run_cli
from cli.v1 import run_cli

# Agent Definitions
from my_agents import triage_agent
from my_agents import web_search_agent
from my_agents import filesystem_agent
from my_agents import ideation_agent
from my_agents import study_agent
from my_agents import analysis_agent

# Agent handoffs
triage_agent.add_handoffs([web_search_agent, filesystem_agent])
web_search_agent.add_handoffs([])
filesystem_agent.add_handoffs([])
analysis_agent.add_handoffs([web_search_agent, filesystem_agent])
ideation_agent.add_handoffs([web_search_agent])
study_agent.add_handoffs([web_search_agent, filesystem_agent, analysis_agent])

# Agent registry
agents = {
    "triage": triage_agent.agent,
    "web": web_search_agent.agent,
    "fs": filesystem_agent.agent,
    "idea": ideation_agent.agent,
    "study": study_agent.agent,
    "analysis": analysis_agent.agent,
}


async def main():
    """Main conversation loop"""
    await run_cli(agents, triage_agent.agent, use_context_agent=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 System shutdown by user")
    except Exception as e:
        print(f"\n❌ System error: {e}")
