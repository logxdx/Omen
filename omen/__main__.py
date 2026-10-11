"""Entry point: `python -m omen` (chat) or `python -m omen eval` (small-model evals).

The line-based chat here is a stopgap until the Textual TUI (Phase 5).
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path

from omen.config import SESSIONS_DIR, main_model
from omen.core import Agent, Session, ToolRegistry
from omen.core.events import (
    ReasoningContent,
    RunError,
    RunFinished,
    TextMessageContent,
    TextMessageEnd,
    ToolCallResult,
    ToolCallStart,
)
from omen.core.llm import LiteLLMClient

DIM, RED, RESET = "\033[2m", "\033[31m", "\033[0m"


def system_prompt() -> str:
    now = datetime.now().astimezone()
    return (
        "You are Jarvis, a concise personal assistant. "
        "Answer in plain sentences. Use a tool only when you need information you don't have.\n"
        f"Current date and time: {now:%A, %d %B %Y, %H:%M %Z}."
    )


async def chat(session_path: Path | None, show_reasoning: bool) -> None:
    session = Session(session_path) if session_path else Session.create(SESSIONS_DIR)
    agent = Agent(LiteLLMClient(main_model()), ToolRegistry(), system_prompt, session)
    loop = asyncio.get_running_loop()
    print(f"{DIM}session: {session.path}  ·  Ctrl+C stops a reply  ·  /quit exits{RESET}")

    while True:
        try:
            text = (await asyncio.to_thread(input, "\n> ")).strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not text:
            continue
        if text in ("/quit", "/exit"):
            return

        loop.add_signal_handler(signal.SIGINT, agent.abort)
        try:
            async for event in agent.run(text):
                if isinstance(event, TextMessageContent):
                    print(event.delta, end="", flush=True)
                elif isinstance(event, TextMessageEnd):
                    print()
                elif isinstance(event, ReasoningContent) and show_reasoning:
                    print(f"{DIM}{event.delta}{RESET}", end="", flush=True)
                elif isinstance(event, ToolCallStart):
                    print(f"{DIM}→ {event.name}{RESET}")
                elif isinstance(event, ToolCallResult) and event.error:
                    print(f"{RED}  {event.error}: {event.content[:200]}{RESET}")
                elif isinstance(event, RunError):
                    print(f"{RED}{event.message}{RESET}")
                elif isinstance(event, RunFinished) and event.reason != "done":
                    print(f"{DIM}[{event.reason}]{RESET}")
        finally:
            loop.remove_signal_handler(signal.SIGINT)


def main() -> None:
    parser = argparse.ArgumentParser(prog="omen")
    sub = parser.add_subparsers(dest="command")
    chat_p = sub.add_parser("chat", help="chat in the terminal (default)")
    chat_p.add_argument("--session", type=Path, help="resume a session file")
    chat_p.add_argument("--reasoning", action="store_true", help="show model reasoning")
    eval_p = sub.add_parser("eval", help="run the small-model eval suite")
    eval_p.add_argument("--only", nargs="*", help="task ids to run")
    eval_p.add_argument("--repeat", type=int, default=1, help="runs per task")
    args = parser.parse_args()

    if args.command == "eval":
        from evals.run import run_suite

        sys.exit(asyncio.run(run_suite(only=args.only, repeat=args.repeat)))
    asyncio.run(chat(getattr(args, "session", None), getattr(args, "reasoning", False)))


if __name__ == "__main__":
    main()
