"""Entry point: `python -m omen` (chat) or `python -m omen eval` (small-model evals).

The line-based chat here is a stopgap until the Textual TUI (Phase 5). Lines you
type while Omen is working are queued and delivered after the current step.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

from agents import Agent

from omen.config import SESSIONS_DIR, main_model
from omen.core import Runtime, Session
from omen.core.events import (
    Custom,
    ReasoningContent,
    RunError,
    RunFinished,
    SubagentEvent,
    TextMessageContent,
    TextMessageEnd,
    ToolCallResult,
    ToolCallStart,
)
from omen.core.models import make_model, make_settings

DIM, RED, RESET = "\033[2m", "\033[31m", "\033[0m"


def system_prompt(_context: object, _agent: object) -> str:
    now = datetime.now().astimezone()
    return (
        "You are Jarvis, a concise personal assistant. "
        "Answer in plain sentences. Use a tool only when you need information you don't have.\n"
        f"Current date and time: {now:%A, %d %B %Y, %H:%M %Z}."
    )


def build_agent() -> Agent:
    config = main_model()
    return Agent(
        name="Jarvis",
        instructions=system_prompt,
        model=make_model(config),
        model_settings=make_settings(config),
    )


def render(event: object, show_reasoning: bool) -> None:
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
    elif isinstance(event, SubagentEvent):
        inner = event.event
        if isinstance(inner, ToolCallStart):
            print(f"{DIM}  [{event.persona}] → {inner.name}{RESET}")
    elif isinstance(event, Custom) and event.name == "message_injected":
        print(f"{DIM}(delivered: {event.value}){RESET}")
    elif isinstance(event, RunError):
        print(f"{RED}{event.message}{RESET}")
    elif isinstance(event, RunFinished) and event.reason != "done":
        print(f"{DIM}[{event.reason}]{RESET}")


async def chat(session_path: Path | None, show_reasoning: bool) -> None:
    session = Session(session_path) if session_path else Session.create(SESSIONS_DIR)
    runtime = Runtime(build_agent(), session)
    loop = asyncio.get_running_loop()
    lines: asyncio.Queue[str | None] = asyncio.Queue()

    def read_stdin() -> None:
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                loop.call_soon_threadsafe(lines.put_nowait, None)
                return
            loop.call_soon_threadsafe(lines.put_nowait, line)

    threading.Thread(target=read_stdin, daemon=True).start()
    print(f"{DIM}session: {session.path}  ·  type while it works to steer  ·  Ctrl+C stops  ·  /quit{RESET}")

    carry: list[str] = []
    quitting = False
    while not quitting:
        if carry:
            text, carry = "\n".join(carry), []
        else:
            print("\n> ", end="", flush=True)
            line = await lines.get()
            if line is None or line.strip() in ("/quit", "/exit"):
                return
            text = line.strip()
            if not text:
                continue

        async def forward_typing() -> None:
            nonlocal quitting
            while True:
                line = await lines.get()
                if line is None or line.strip() in ("/quit", "/exit"):
                    quitting = True
                    runtime.abort()
                    return
                if line.strip():
                    runtime.send(line.strip())
                    print(f"{DIM}(queued){RESET}")

        forwarder = asyncio.create_task(forward_typing())
        loop.add_signal_handler(signal.SIGINT, runtime.abort)
        try:
            async for event in runtime.run(text):
                render(event, show_reasoning)
        finally:
            loop.remove_signal_handler(signal.SIGINT)
            forwarder.cancel()
        carry = [] if quitting else runtime.queue.drain()  # typed after the run's last delivery point


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
