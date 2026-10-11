"""Omen's terminal UI (Textual).

    python -m omen            # or: python -m omen tui --persona writer

- Enter sends. While Omen works, Enter steers it (delivered after the current step);
  when Omen asks a question, Enter (or picking an option) answers it.
- Esc stops the current run. Ctrl+P opens the command palette, Ctrl+T the branch tree.
- Slash commands: /help /personas /persona <name> /skills /skill <name> /reload /new /tree /quit
"""

from __future__ import annotations

import json
from typing import Any, Callable

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Collapsible, Footer, Input, Markdown, OptionList, Static, Tree

from omen.assistant import Assistant, build_assistant
from omen.config import SESSIONS_DIR, main_model
from omen.core import Runtime, Session
from omen.core import events as ev
from omen.core.skills import loaded
from omen.tui.art import omen as OMEN_ART
from omen.tui.render import RENDERERS, render
from omen.ui.extract import Extractor, components_for
from omen.ui.history import history

HELP = (
    "**Enter** send · steer while working · answer questions   **Esc** stop   **Ctrl+P** commands   **Ctrl+T** branches\n\n"
    "`/personas` `/persona <name>` `/skills` `/skill <name>` `/reload` `/new` `/tree` `/quit`"
)


TEXT_COMPONENTS = {"chart", "card"}  # components extracted from replies in the TUI


class Plain(Static):
    """Static text without Rich markup parsing (model output contains brackets)."""

    def __init__(self, text: str = "", **kwargs: Any):
        super().__init__(text, markup=False, **kwargs)


class Note(Plain):
    """A dim one-line note in the transcript."""


class UserMessage(Plain):
    pass


class ErrorMessage(Plain):
    pass


class Transcript:
    """Turns Omen events into widgets inside `container` (the main transcript or a subagent block)."""

    def __init__(self, app: OmenApp, container: Widget):
        self.app = app
        self.container = container
        self.streams: dict[str, Any] = {}
        self.reasoning: Plain | None = None
        self.reasoning_text = ""
        self.tools: dict[str, tuple[Collapsible, Vertical, str]] = {}
        self.subagents: dict[str, Transcript] = {}
        self.subagent_blocks: dict[str, Collapsible] = {}

    async def mount(self, widget: Widget, after: Widget | None = None) -> Widget:
        if after is not None:
            await self.container.mount(widget, after=after)
        else:
            await self.container.mount(widget)
        self.app.scroll_down()
        return widget

    async def handle(self, event: ev.Event) -> None:
        if isinstance(event, ev.SubagentEvent):
            await self._subagent(event)
        elif isinstance(event, ev.StepStarted):
            self.reasoning = None
        elif isinstance(event, ev.ReasoningContent):
            if self.reasoning is None:
                self.reasoning_text = ""
                self.reasoning = Plain("", classes="reasoning-text")
                await self.mount(Collapsible(self.reasoning, title="thinking", classes="reasoning"))
            self.reasoning_text += event.delta
            self.reasoning.update(self.reasoning_text)
        elif isinstance(event, ev.TextMessageStart):
            self.reasoning = None
            md = await self.mount(Markdown("", classes="assistant"))
            stream = Markdown.get_stream(md)
            self.streams[event.message_id] = stream
        elif isinstance(event, ev.TextMessageContent):
            if event.message_id in self.streams:
                await self.streams[event.message_id].write(event.delta)
        elif isinstance(event, ev.TextMessageEnd):
            stream = self.streams.pop(event.message_id, None)
            if stream is not None:
                await stream.stop()
        elif isinstance(event, ev.ToolCallStart):
            self.reasoning = None
            body = Vertical(classes="tool-body")
            row = Collapsible(body, title=f"→ {event.name}", classes="tool")
            await self.mount(row)
            self.tools[event.tool_call_id] = (row, body, event.name)
        elif isinstance(event, ev.ToolCallArgs):
            if event.tool_call_id in self.tools and event.delta not in ("", "{}"):
                _, body, _ = self.tools[event.tool_call_id]
                await body.mount(Plain(_compact_args(event.delta), classes="tool-args"))
        elif isinstance(event, ev.ToolCallResult):
            await self._tool_result(event)
        elif isinstance(event, ev.UIComponent):
            widget = render(event.payload)
            if widget is not None:
                await self.mount(widget)
        elif isinstance(event, ev.UserQuestion):
            await self.mount(Question(event))
        elif isinstance(event, ev.Custom):
            if event.name == "skill_loaded":
                await self.mount(Note(f"⚙ skill: {event.value['skill']} ({event.value.get('by', '')})"))
            elif event.name == "message_injected":
                await self.mount(UserMessage(f"› {event.value}"))
            elif event.name == "usage":
                self.app.add_usage(event.value)
        elif isinstance(event, ev.RunError):
            await self.mount(ErrorMessage(f"✗ {event.message}"))
        elif isinstance(event, ev.RunFinished) and event.reason != "done":
            await self.mount(Note(f"[{event.reason}]"))

    async def _tool_result(self, event: ev.ToolCallResult) -> None:
        entry = self.tools.get(event.tool_call_id)
        if entry is None:
            return
        row, body, name = entry
        row.title = f"{'✗' if event.error else '✓'} {name}"
        if event.error:
            row.add_class("error")
        text = event.content if len(event.content) < 1500 else event.content[:1500] + " …"
        await body.mount(Plain(text, classes="tool-result"))
        block = self.subagent_blocks.get(event.tool_call_id)
        if block is not None:
            block.collapsed = True  # the persona is done; its answer is in the result
        widget = render(event.details)
        if widget is not None:
            await self.mount(widget, after=block or row)

    async def _subagent(self, event: ev.SubagentEvent) -> None:
        sub = self.subagents.get(event.tool_call_id)
        if sub is None:
            inner = Vertical(classes="subagent-body")
            block = Collapsible(inner, title=f"↳ {event.persona}", collapsed=False, classes="subagent")
            anchor = self.tools.get(event.tool_call_id, (None,))[0]
            await self.mount(block, after=anchor)
            self.subagent_blocks[event.tool_call_id] = block
            sub = self.subagents[event.tool_call_id] = Transcript(self.app, inner)
        await sub.handle(event.event)


class Question(Vertical):
    """An ask_user question: pick an option or type the answer."""

    def __init__(self, event: ev.UserQuestion):
        super().__init__(classes="question")
        self.event = event

    def compose(self) -> ComposeResult:
        yield Plain(f"? {self.event.question}", classes="question-text")
        if self.event.options:
            yield OptionList(*self.event.options)

    def on_mount(self) -> None:
        if self.event.options:
            self.query_one(OptionList).focus()

    @on(OptionList.OptionSelected)
    def picked(self, message: OptionList.OptionSelected) -> None:
        self.app.answer(str(message.option.prompt))


class BranchTree(ModalScreen[str | None]):
    """Pick any point in the session to continue from (Esc to cancel)."""

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, session: Session):
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        tree: Tree[str | None] = Tree("session", data=None)
        tree.root.expand()
        on_path = {e["id"] for e in self.session.path_to()}
        children: dict[str | None, list[dict]] = {}
        for entry in self.session.entries.values():
            if entry["type"] == "item":
                children.setdefault(entry["parent_id"], []).append(entry)

        def add(node, parent_id):
            for entry in children.get(parent_id, []):
                label = _entry_label(entry)
                if entry["id"] == self.session.leaf:
                    label = f"● {label}"
                elif entry["id"] in on_path:
                    label = f"· {label}"
                child = node.add(Text(label), data=entry["id"], expand=entry["id"] in on_path)
                add(child, entry["id"])

        add(tree.root, None)
        with Vertical(id="tree-box"):
            yield Static("Branches — Enter: continue from here · Esc: cancel", id="tree-title")
            yield tree

    @on(Tree.NodeSelected)
    def chosen(self, message: Tree.NodeSelected) -> None:
        if message.node.data:
            self.dismiss(message.node.data)


class OmenCommands(Provider):
    """Command palette (Ctrl+P): personas, skills, sessions."""

    async def search(self, query: str) -> Hits:
        app = self.app
        assert isinstance(app, OmenApp)
        matcher = self.matcher(query)
        commands: list[tuple[str, Callable[[], Any], str]] = [
            ("New session", app.new_session, "Start a fresh conversation"),
            ("Branches", app.action_tree, "Continue from any earlier point"),
            ("Reload skills", lambda: app.run_command("/reload"), "Re-scan skill folders"),
        ]
        for persona in app.assistant.personas.values():
            if persona.main:
                commands.append((f"Persona: {persona.name}", lambda n=persona.name: app.run_command(f"/persona {n}"), persona.description))
        for skill in app.assistant.skills.skills.values():
            commands.append((f"Load skill: {skill.name}", lambda n=skill.name: app.run_command(f"/skill {n}"), skill.description))
        for name, action, help_text in commands:
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), action, help=help_text)


class OmenApp(App):
    TITLE = "omen"
    COMMANDS = App.COMMANDS | {OmenCommands}
    BINDINGS = [
        Binding("escape", "abort", "Stop"),
        Binding("ctrl+t", "tree", "Branches"),
        Binding("ctrl+n", "new_session", "New"),
        Binding("ctrl+q", "quit", "Quit"),
    ]
    CSS = """
    Screen { background: $background; }
    #header { height: 1; padding: 0 1; background: $panel; color: $text-muted; }
    #transcript { padding: 0 1; }
    #banner { color: magenta; text-style: bold; }
    UserMessage { color: ansi_bright_blue; text-style: bold; margin: 1 0 0 0; }
    Markdown.assistant { margin: 0; padding: 0; background: transparent; }
    Note { color: $text-muted; }
    ErrorMessage { color: ansi_bright_red; text-style: bold; }
    Collapsible { border: none; padding: 0; margin: 0; background: transparent; height: auto; }
    .tool-body, .subagent-body { height: auto; }
    Collapsible.tool > CollapsibleTitle { color: ansi_bright_magenta; }
    Collapsible.tool.error > CollapsibleTitle { color: ansi_bright_red; }
    Collapsible.reasoning > CollapsibleTitle { color: $text-muted; text-style: italic; }
    Collapsible.subagent { border-left: thick magenta; padding-left: 1; }
    .tool-args { color: $text-muted; }
    .tool-result { color: $text; }
    .reasoning-text { color: $text-muted; }
    .component { margin: 0 0 0 2; }
    .question { border: round magenta; padding: 0 1; height: auto; }
    .question-text { text-style: bold; }
    .question OptionList { height: auto; max-height: 8; }
    #status { height: 1; padding: 0 1; color: $text-muted; }
    #prompt { margin: 0 1; }
    #tree-box { width: 90%; height: 80%; border: round magenta; background: $panel; }
    #tree-title { padding: 0 1; color: $text-muted; }
    BranchTree { align: center middle; }
    """

    def __init__(
        self,
        *,
        persona: str | None = None,
        session: Session | None = None,
        assistant_factory: Callable[..., Assistant] = build_assistant,
        extractor: Extractor | None = None,
        use_router: bool = True,
    ):
        super().__init__()
        self.assistant_factory = assistant_factory
        self.assistant = assistant_factory(persona=persona, use_router=use_router)
        self.session = session or Session.create(SESSIONS_DIR)
        self.extractor = extractor if extractor is not None else Extractor()
        self.runtime = Runtime.for_assistant(
            self.assistant, self.session, components=self._components, ui=set(RENDERERS),
        )
        self.usage: dict = {}
        self.transcript: Transcript | None = None

    async def _components(self, text: str, ui: set[str] | None):
        # The Markdown widget already shows tables and option lists; only add what it can't draw.
        return await components_for(text, self.extractor, TEXT_COMPONENTS)

    # -- layout ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        yield Plain("", id="header")
        yield VerticalScroll(id="transcript")
        yield Plain("", id="status")
        yield Input(placeholder="Message Omen…  (/help)", id="prompt")
        yield Footer()

    async def on_mount(self) -> None:
        scroll = self.query_one("#transcript", VerticalScroll)
        self.transcript = Transcript(self, scroll)
        await scroll.mount(Plain(OMEN_ART[2].strip("\n"), id="banner"))
        if self.session.items():
            await self.replay()
        self.refresh_status()
        self.query_one("#prompt", Input).focus()

    def add_usage(self, usage: dict) -> None:
        """Accumulate token usage for the session (the status bar shows the prompt-cache hit rate)."""
        for key in ("input_tokens", "output_tokens", "cached_tokens"):
            self.usage[key] = self.usage.get(key, 0) + (usage.get(key) or 0)

    def scroll_down(self) -> None:
        self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)

    def refresh_status(self, state: str = "ready") -> None:
        skills = ", ".join(loaded(self.runtime.state)) or "none"
        self.query_one("#header", Plain).update(
            f"omen · persona: {self.assistant.persona.name} · model: {main_model().model} · skills: {skills}"
        )
        tokens = ""
        if self.usage.get("input_tokens"):
            hit = 100 * self.usage.get("cached_tokens", 0) / self.usage["input_tokens"]
            tokens = f" · {self.usage['input_tokens'] + self.usage.get('output_tokens', 0)} tokens · cache {hit:.0f}%"
        session = self.session.path.name if self.session.path else "in memory"
        self.query_one("#status", Plain).update(f"{state}{tokens} · {session}")

    # -- input ----------------------------------------------------------------------- #

    @on(Input.Submitted, "#prompt")
    async def submitted(self, message: Input.Submitted) -> None:
        text = message.value.strip()
        message.input.value = ""
        if not text:
            return
        if text.startswith("/"):
            await self.run_command(text)
        elif self.runtime.pending_question is not None:
            self.answer(text)
        elif self.runtime.running:
            self.runtime.send(text)
            await self.transcript.mount(Note(f"(queued) {text}"))
        else:
            self.start_run(text)

    def answer(self, text: str) -> None:
        if self.runtime.answer(text):
            for question in self.query(Question):
                question.remove()
            self.call_later(self.transcript.mount, Note(f"› {text}"))
            self.query_one("#prompt", Input).focus()

    def start_run(self, text: str) -> None:
        self.run_agent(text)

    @work(exclusive=True, group="agent")
    async def run_agent(self, text: str) -> None:
        await self.transcript.mount(UserMessage(f"› {text}"))
        self.refresh_status("working… (Esc to stop)")
        async for event in self.runtime.run(text):
            await self.transcript.handle(event)
            if isinstance(event, (ev.Custom, ev.StepStarted)):
                self.refresh_status("working… (Esc to stop)")
        self.refresh_status()
        carry = self.runtime.queue.drain()  # typed after the run's last delivery point
        if carry:
            self.call_later(self.start_run, "\n".join(carry))

    # -- actions / commands ------------------------------------------------------------- #

    def action_abort(self) -> None:
        if self.runtime.running:
            self.runtime.abort()

    def action_new_session(self) -> None:
        self.call_later(self.new_session)

    async def new_session(self) -> None:
        if self.runtime.running:
            self.runtime.abort()
        self.session = Session.create(SESSIONS_DIR)
        self.runtime.session = self.session
        self.usage = {}
        await self.clear_transcript()
        await self.transcript.mount(Note("new session"))
        self.refresh_status()

    def action_tree(self) -> None:
        if self.runtime.running:
            self.notify("Stop the current run first (Esc).")
            return
        self.push_screen(BranchTree(self.session), self.branch_to)

    async def branch_to(self, entry_id: str | None) -> None:
        if not entry_id:
            return
        self.session.branch(entry_id)
        await self.clear_transcript()
        await self.replay()
        await self.transcript.mount(Note("continuing from here"))

    async def clear_transcript(self) -> None:
        scroll = self.query_one("#transcript", VerticalScroll)
        await scroll.remove_children()
        self.transcript = Transcript(self, scroll)

    async def replay(self) -> None:
        """Re-render the current branch from the session."""
        for message in history(self.session):
            role = message["role"]
            if role == "user":
                await self.transcript.mount(UserMessage(f"› {message['content']}"))
            elif role == "assistant" and message["content"]:
                await self.transcript.mount(Markdown(message["content"], classes="assistant"))
            elif role == "tool_call":
                await self.transcript.handle(ev.ToolCallStart(message["id"], message["name"]))
                await self.transcript.handle(ev.ToolCallArgs(message["id"], message.get("arguments") or ""))
            elif role == "tool":
                await self.transcript.handle(
                    ev.ToolCallResult(message["id"], message["name"], str(message["content"] or ""), message["ui"], None)
                )

    async def run_command(self, text: str) -> None:
        name, _, arg = text.partition(" ")
        arg = arg.strip()
        note = self.transcript.mount
        if name in ("/quit", "/exit"):
            self.exit()
        elif name in ("/help", "/?"):
            await note(Markdown(HELP, classes="assistant"))
        elif name == "/new":
            await self.new_session()
        elif name == "/tree":
            self.action_tree()
        elif name == "/personas":
            lines = [
                f"{'*' if p.name == self.assistant.persona.name else ' '} {p.name}: {p.description}"
                for p in self.assistant.personas.values()
            ]
            await note(Note("\n".join(lines)))
        elif name == "/persona" and arg:
            if self.runtime.running:
                await note(Note("stop the current run first"))
                return
            try:
                self.assistant = self.assistant.switch(arg.lower())
            except KeyError:
                await note(ErrorMessage(f"no main persona named {arg}"))
                return
            self.runtime.attach(self.assistant)
            await note(Note(f"persona: {self.assistant.persona.name}"))
        elif name == "/skills":
            active = loaded(self.runtime.state)
            lines = [
                f"{'*' if s.name in active else ' '} {s.name}: {s.description}"
                for s in self.assistant.skills.skills.values()
            ]
            await note(Note("\n".join(lines)))
        elif name == "/skill" and arg:
            if self.assistant.skills.load(arg, self.runtime.state):
                await note(Note(f"⚙ skill: {arg}"))
            else:
                await note(ErrorMessage(f"no skill named {arg}"))
        elif name == "/reload":
            self.assistant.reload()
            await note(Note(f"reloaded {len(self.assistant.skills.skills)} skills"))
        else:
            await note(ErrorMessage(f"unknown command {name} (/help)"))
        self.refresh_status()


def _compact_args(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:300]
    parts = [f"{k}={v!r}" if not isinstance(v, str) or len(v) < 80 else f"{k}={v[:77]!r}…" for k, v in data.items()]
    return ", ".join(parts)[:300]


def _entry_label(entry: dict) -> str:
    data = entry["data"]
    meta = entry.get("meta") or {}
    prefix = f"↳ {meta['persona']}: " if meta.get("persona") else ""
    role, kind = data.get("role"), data.get("type")
    if role in ("user", "assistant"):
        content = data.get("content")
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        text = " ".join(str(content or "").split())
        return f"{prefix}{role}: {text[:70]}"
    if kind == "function_call":
        return f"{prefix}→ {data.get('name')}"
    if kind == "function_call_output":
        return f"{prefix}  result: {' '.join(str(data.get('output', '')).split())[:50]}"
    return f"{prefix}{kind or role}"


def run_tui(persona: str | None = None, session_path=None, use_router: bool = True) -> None:
    session = Session(session_path) if session_path else None
    OmenApp(persona=persona, session=session, use_router=use_router).run()
