import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()  # picks up ANTHROPIC_API_KEY for the agent subprocess

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from cli import run_cli


async def main():
    await run_cli()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 System shutdown by user")
    except Exception as e:
        print(f"\n❌ System error: {e}")
