import json
import time

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    ToolUseBlock,
)
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from agents import SUBAGENTS, SYSTEM_PROMPT
from art import get_art
from config import ALLOWED_TOOLS, THEME, VERSION

CONSOLE_WIDTH = 150
console = Console(theme=THEME, color_system="truecolor", width=CONSOLE_WIDTH)

COMMANDS = {
    "help": {"aliases": ["/help", "/h"], "description": "Show this help message"},
    "clear": {"aliases": ["/clear", "/c"], "description": "Clear screen"},
    "voice": {"aliases": ["/voice", "/v"], "description": "Toggle voice mode on/off"},
    "new": {"aliases": ["/new", "/n"], "description": "Start a fresh session"},
    "quit": {"aliases": ["/quit", "/exit", "/q"], "description": "Exit the application"},
}


def make_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=ALLOWED_TOOLS,
        agents=SUBAGENTS,
        permission_mode="acceptEdits",
        include_partial_messages=True,
    )


def welcome_panel():
    console.clear()

    commands_table = Table.grid(padding=(0, 4))
    commands_table.add_column(style="accent.bold", justify="right")
    commands_table.add_column(style="assistant", justify="left")
    for cmd in COMMANDS.values():
        commands_table.add_row(", ".join(cmd["aliases"]), cmd["description"])

    console.print(
        Panel(
            Group(
                Text(get_art(), style="accent.bold", justify="center"),
                Text("Quick Controls\n", style="title"),
                commands_table,
            ),
            title=f"Version: {VERSION}",
            title_align="right",
            padding=(1, 2),
            box=box.ROUNDED,
            border_style="accent",
        ),
        justify="center",
    )


def help_panel():
    help_table = Table(
        title="Slash Commands",
        show_header=True,
        header_style="title",
        expand=True,
        box=box.ROUNDED,
        padding=(0, 1),
    )
    help_table.add_column("Command", style="accent.bold")
    help_table.add_column("Description", style="assistant")
    for cmd in COMMANDS.values():
        help_table.add_row(", ".join(cmd["aliases"]), cmd["description"])
    console.print(help_table, justify="center")


def _tool_line(block: ToolUseBlock) -> Text:
    args = ""
    if block.input:
        args = json.dumps(block.input)
        if len(args) > 100:
            args = args[:100] + "…"
    return Text(f"» {block.name} {args}", style="dim")


def _display(status_lines: list[Text], response: str, elapsed: float | None = None):
    parts = []
    if status_lines:
        parts.append(Group(*status_lines[-4:]))
    parts.append(
        Panel(
            Markdown(response, style="assistant"),
            title=Text("Omen", style="title"),
            title_align="left",
            subtitle=f"({elapsed:.2f}s)" if elapsed is not None else None,
            subtitle_align="right",
            border_style="accent",
            padding=(1, 1),
        )
    )
    return Group(*parts)


async def stream_response(client: ClaudeSDKClient, user_msg: str) -> str:
    """Send one prompt and stream the response into a live Rich panel."""
    start = time.time()
    response = ""
    status_lines: list[Text] = []
    final_text = ""

    await client.query(user_msg)

    with Live(_display(status_lines, response), console=console, refresh_per_second=4) as live:
        try:
            async for message in client.receive_response():
                if isinstance(message, StreamEvent):
                    # Only stream top-level assistant text; skip subagent chatter.
                    if message.parent_tool_use_id is not None:
                        continue
                    event = message.event
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            response += delta.get("text", "")

                elif isinstance(message, AssistantMessage):
                    if message.parent_tool_use_id is not None:
                        continue
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            status_lines.append(_tool_line(block))

                elif isinstance(message, ResultMessage):
                    if message.result:
                        final_text = message.result
                    if message.is_error:
                        status_lines.append(
                            Text(f"! {message.subtype}", style="error")
                        )

                live.update(_display(status_lines, response))

            live.update(_display(status_lines, response or final_text, time.time() - start))

        except KeyboardInterrupt:
            await client.interrupt()
            console.print("\n[error]Interrupted by user[/error]")

    return final_text or response


async def run_cli():
    from claude_agent_sdk import CLINotFoundError

    voice = None
    voice_mode = False

    welcome_panel()

    client = ClaudeSDKClient(options=make_options())
    await client.connect()

    try:
        while True:
            if voice_mode:
                try:
                    user_msg = voice.listen()
                    console.print(f"\n[user]You:[/user] {user_msg}\n")
                except Exception as e:
                    console.print(f"[error]STT Error: {e}[/error]")
                    voice_mode = False
                    continue
                if not user_msg:
                    console.print("[warning]No speech detected. Please try again.[/warning]")
                    continue
            else:
                try:
                    user_msg = Prompt.ask("\n[dim]You[/dim]")
                except (EOFError, KeyboardInterrupt):
                    break
                if not user_msg.strip():
                    continue

            cmd = user_msg.lower().split()[0]

            if cmd in COMMANDS["quit"]["aliases"]:
                break
            elif cmd in COMMANDS["help"]["aliases"]:
                help_panel()
                continue
            elif cmd in COMMANDS["clear"]["aliases"]:
                console.clear()
                continue
            elif cmd in COMMANDS["new"]["aliases"]:
                await client.disconnect()
                client = ClaudeSDKClient(options=make_options())
                await client.connect()
                console.print("[dim]Started a fresh session.[/dim]")
                continue
            elif cmd in COMMANDS["voice"]["aliases"]:
                if voice_mode:
                    voice_mode = False
                    console.print("[accent.bold]Text mode[/accent.bold]")
                else:
                    if voice is None:
                        console.print("[dim]Loading voice pipeline...[/dim]")
                        from voice import Voice

                        voice = Voice()
                    voice_mode = True
                    console.print("[accent.bold]Voice mode[/accent.bold]")
                continue

            try:
                result = await stream_response(client, user_msg)
            except CLINotFoundError:
                console.print(
                    "[error]Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code[/error]"
                )
                break
            except Exception as e:
                console.print(f"[error]Error: {e}[/error]")
                continue

            if voice_mode and voice and result:
                voice.speak(result, user_query=user_msg)
    finally:
        await client.disconnect()
        if voice is not None:
            voice.shutdown()
