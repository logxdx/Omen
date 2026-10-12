"""Entry point: `python -m omen` (TUI), `omen chat` (line chat), `omen voice` (speech, needs the
`voice` extra), `omen serve` (AG-UI server), `omen eval`.

`python -m omen` opens the Textual TUI; `omen chat` is the plain line chat. In it, lines you
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
HELP = "/personas  /persona <name>  /skills  /skill <name>  /reload  /quit   ·   type while it works to steer   ·   Ctrl+C stops"


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


def command(text: str, assistant: Assistant, runtime: Runtime) -> Assistant | None:
    """Handle a slash command. Returns the (possibly new) assistant, or None if `text` wasn't one."""
    if text == "/personas":
        for persona in assistant.personas.values():
            mark = "*" if persona.name == assistant.persona.name else " "
            roles = "/".join(r for r, on in (("main", persona.main), ("delegate", persona.delegate)) if on)
            print(f"{mark} {persona.name} [{roles}]: {persona.description}")
        return assistant
    if text.startswith("/persona "):
        name = text.split(maxsplit=1)[1].strip().lower()
        try:
            switched = assistant.switch(name)
        except KeyError:
            print(f"{RED}no main persona named {name}{RESET}")
            return assistant
        runtime.attach(switched)
        print(f"{DIM}(persona: {name}){RESET}")
        return switched
    if text == "/skills":
        active = loaded(runtime.state)
        for skill in assistant.skills.skills.values():
            mark = "*" if skill.name in active else " "
            print(f"{mark} {skill.name}: {skill.description}")
        return assistant
    if text.startswith("/skill "):
        name = text.split(maxsplit=1)[1].strip()
        if assistant.skills.load(name, runtime.state):
            print(f"{DIM}(skill: {name}){RESET}")
        else:
            print(f"{RED}no skill named {name}{RESET}")
        return assistant
    if text == "/reload":
        assistant.reload()
        print(f"{DIM}(reloaded {len(assistant.skills.skills)} skills){RESET}")
        return assistant
    if text in ("/help", "/?"):
        print(HELP)
        return assistant
    return None


async def chat(session_path: Path | None, show_reasoning: bool, use_router: bool, persona: str | None) -> None:
    session = Session(session_path) if session_path else Session.create(SESSIONS_DIR)
    assistant = build_assistant(use_router=use_router, persona=persona)
    runtime = Runtime.for_assistant(assistant, session)
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
            if not text:
                continue
            if text.startswith("/"):
                handled = command(text, assistant, runtime)
                if handled is not None:
                    assistant = handled
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
    tui_p = sub.add_parser("tui", help="terminal UI (default)")
    tui_p.add_argument("--session", type=Path, help="resume a session file")
    tui_p.add_argument("--persona", help="main persona (default: OMEN_PERSONA or omen)")
    tui_p.add_argument("--no-router", action="store_true", help="don't auto-load skills by keyword")
    chat_p = sub.add_parser("chat", help="line-based chat (no TUI)")
    chat_p.add_argument("--session", type=Path, help="resume a session file")
    chat_p.add_argument("--reasoning", action="store_true", help="show model reasoning")
    chat_p.add_argument("--no-router", action="store_true", help="don't auto-load skills by keyword")
    chat_p.add_argument("--persona", help="main persona (default: OMEN_PERSONA or omen)")
    voice_p = sub.add_parser("voice", help="talk to Omen (needs `uv sync --extra voice` and a TTS server)")
    voice_p.add_argument("--session", type=Path, help="resume a session file")
    voice_p.add_argument("--no-router", action="store_true", help="don't auto-load skills by keyword")
    voice_p.add_argument("--persona", help="main persona (default: OMEN_PERSONA or omen)")
    serve_p = sub.add_parser("serve", help="AG-UI server for the web UI")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)
    schema_p = sub.add_parser("schema", help="print the UI component JSON Schema")
    schema_p.add_argument("--ts", action="store_true", help="print TypeScript types instead")
    eval_p = sub.add_parser("eval", help="run the small-model eval suite")
    eval_p.add_argument("--only", nargs="*", help="task ids to run")
    eval_p.add_argument("--repeat", type=int, default=1, help="runs per task")
    eval_p.add_argument("--extract", action="store_true", help="run the UI extractor eval instead")
    args = parser.parse_args()

    if args.command == "serve":
        from omen.server import serve

        serve(args.host, args.port)
        return
    if args.command == "schema":
        if args.ts:
            from omen.ui.tsgen import typescript

            print(typescript(), end="")
            return
        import json

        from omen.ui.components import json_schema

        print(json.dumps(json_schema(), indent=2))
        return
    if args.command == "eval":
        if args.extract:
            from evals.extract import run_extract_suite

            sys.exit(asyncio.run(run_extract_suite(repeat=args.repeat)))
        from evals.run import run_suite

        sys.exit(asyncio.run(run_suite(only=args.only, repeat=args.repeat)))
    if args.command == "voice":
        from omen.voice.frontend import run_voice

        session = Session(args.session) if args.session else Session.create(SESSIONS_DIR)
        assistant = build_assistant(use_router=not args.no_router, persona=args.persona)
        if run_voice(Runtime.for_assistant(assistant, session), lambda event: render(event, False)):
            return
        print("(falling back to the text chat)")
        args.session = session.path if session.entries else args.session
    if args.command in (None, "tui"):
        try:
            from omen.tui.app import run_tui
        except ImportError:
            if args.command == "tui":
                sys.exit("The TUI needs textual: run `uv sync`.")
            print("(textual not installed; using the line chat — run `uv sync` for the TUI)")
        else:
            run_tui(
                getattr(args, "persona", None),
                getattr(args, "session", None),
                not getattr(args, "no_router", False),
            )
            return
    asyncio.run(
        chat(
            getattr(args, "session", None),
            getattr(args, "reasoning", False),
            not getattr(args, "no_router", False),
            getattr(args, "persona", None),
        )
    )


if __name__ == "__main__":
    main()
