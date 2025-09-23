import asyncio

# Agent Definitions
from my_agents.ideation_agent import create_ideation_agent
from my_agents.web_search_agent import create_web_search_agent
from my_agents.filesystem_agent import create_filesystem_agent
from my_agents.triage_agent import create_triage_agent
from my_agents.study_agent import create_study_agent
from my_agents.memory_agent import create_memory_agent
from my_agents.analysis_agent import create_analysis_agent

# Create agents
ideation_agent = create_ideation_agent()
web_search_agent = create_web_search_agent()
filesystem_agent = create_filesystem_agent()
study_agent = create_study_agent()
memory_agent = create_memory_agent()
analysis_agent = create_analysis_agent()

# triage agent with handoffs to necessary agents
triage_agent = create_triage_agent(handoffs=[web_search_agent, filesystem_agent, memory_agent, analysis_agent])

# Add handoffs to all other agents
filesystem_agent.handoffs.extend([triage_agent])
web_search_agent.handoffs.extend([triage_agent])
memory_agent.handoffs.extend([triage_agent])
analysis_agent.handoffs.extend([triage_agent, filesystem_agent])
ideation_agent.handoffs.extend([triage_agent, web_search_agent, memory_agent])
study_agent.handoffs.extend([triage_agent, web_search_agent, filesystem_agent, memory_agent, analysis_agent])

# Agent registry
agents = {
    "triage": triage_agent,
    "web": web_search_agent,
    "fs": filesystem_agent,
    "idea": ideation_agent,
    "study": study_agent,
    "memory": memory_agent,
    "analysis": analysis_agent,
}

async def main():
    """Main conversation loop"""

    from cli_interface.interface import run_cli

    await run_cli(agents, triage_agent)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 System shutdown by user")
    except Exception as e:
        print(f"\n❌ System error: {e}")
