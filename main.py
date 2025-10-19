import asyncio

from cli.v1 import run_cli

from agent_runtime import get_agent_registry


agents, primary_agent = get_agent_registry()


async def main():
    """Main conversation loop"""
    await run_cli(agents, primary_agent)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 System shutdown by user")
    except Exception as e:
        print(f"\n❌ System error: {e}")
