import asyncio

from cli.v1 import run_cli

async def main():
    """Main conversation loop"""
    await run_cli()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 System shutdown by user")
    except Exception as e:
        print(f"\n❌ System error: {e}")
