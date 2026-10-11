"""Entry point: `python -m omen` (chat) or `python -m omen eval` (small-model evals).

The line-based chat here is a stopgap until the Textual TUI (Phase 5). Lines you
type while Omen is working are queued and delivered after the current step;
when Omen asks a question, the next line you type answers it.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import threading
from pathlib import Path

from omen.assistant import Assistant, build_assistant
from omen.config import SESSIONS_DIR
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
    UserQuestion,
)
from omen.core.skills import loaded

DIM, RED, BOLD, RESET = "\033[2m", "\033[31m", "\033[1m", "\033[0m"
HELP = "/skills  /skill <name>  /reload  /quit   ·   type while it works to steer   ·   Ctrl+C stops"


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
    elif isinstance(event, UserQuestion):
        options = f"  [{' / '.join(event.options)}]" if event.options else ""
        print(f"\n{BOLD}? {event.question}{RESET}{options}\n> ", end="", flush=True)
    elif isinstance(event, SubagentEvent):
        inner = event.event
        if isinstance(inner, ToolCallStart):
            print(f"{DIM}  [{event.persona}] → {inner.name}{RESET}")
    elif isinstance(event, Custom) and event.name == "message_injected":
        print(f"{DIM}(delivered: {event.value}){RESET}")
    elif isinstance(event, Custom) and event.name == "skill_loaded":
        print(f"{DIM}(skill: {event.value['skill']}){RESET}")
    elif isinstance(event, RunError):
        print(f"{RED}{event.message}{RESET}")
    elif isinstance(event, RunFinished) and event.reason != "done":
        print(f"{DIM}[{event.reason}]{RESET}")


def command(text: str, assistant: Assistant, runtime: Runtime) -> bool:
    """Handle a slash command. Returns True if `text` was one."""
    if text == "/skills":
        active = loaded(runtime.state)
        for skill in assistant.skills.skills.values():
            mark = "*" if skill.name in active else " "
            print(f"{mark} {skill.name}: {skill.description}")
        return True
    if text.startswith("/skill "):
        name = text.split(maxsplit=1)[1].strip()
        if assistant.skills.load(name, runtime.state):
            print(f"{DIM}(skill: {name}){RESET}")
        else:
            print(f"{RED}no skill named {name}{RESET}")
        return True
    if text == "/reload":
        assistant.reload()
        print(f"{DIM}(reloaded {len(assistant.skills.skills)} skills){RESET}")
        return True
    if text in ("/help", "/?"):
        print(HELP)
        return True
    return False


async def chat(session_path: Path | None, show_reasoning: bool, use_router: bool) -> None:
    session = Session(session_path) if session_path else Session.create(SESSIONS_DIR)
    assistant = build_assistant(use_router=use_router)
    runtime = Runtime(assistant.agent, session, prepare=assistant.prepare)
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
    print(f"{DIM}session: {session.path}\n{HELP}{RESET}")

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
            if not text or command(text, assistant, runtime):
                continue

        async def forward_typing() -> None:
            nonlocal quitting
            while True:
                line = await lines.get()
                if line is None or line.strip() in ("/quit", "/exit"):
                    quitting = True
                    runtime.abort()
                    return
                if not line.strip():
                    continue
                if runtime.answer(line.strip()):
                    continue
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
    chat_p.add_argument("--no-router", action="store_true", help="don't auto-load skills by keyword")
    eval_p = sub.add_parser("eval", help="run the small-model eval suite")
    eval_p.add_argument("--only", nargs="*", help="task ids to run")
    eval_p.add_argument("--repeat", type=int, default=1, help="runs per task")
    args = parser.parse_args()

    if args.command == "eval":
        from evals.run import run_suite

        sys.exit(asyncio.run(run_suite(only=args.only, repeat=args.repeat)))
    asyncio.run(
        chat(
            getattr(args, "session", None),
            getattr(args, "reasoning", False),
            not getattr(args, "no_router", False),
        )
    )


if __name__ == "__main__":
    main()
