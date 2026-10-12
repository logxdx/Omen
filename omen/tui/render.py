"""TUI renderers: one function per UI component type → a Textual widget.

`render(payload)` takes a UIPayload dict ({type, valid, props, text}); unknown or
invalid components fall back to their text as markdown.
"""

from __future__ import annotations

import difflib
from typing import Any, Callable

from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.widget import Widget
from textual.widgets import DataTable, Markdown, Static

Renderer = Callable[[dict, str], Widget]
RENDERERS: dict[str, Renderer] = {}


def renderer(kind: str):
    def register(fn: Renderer) -> Renderer:
        RENDERERS[kind] = fn
        return fn

    return register


def render(ui: dict | None) -> Widget | None:
    if not isinstance(ui, dict):
        return None
    fn = RENDERERS.get(str(ui.get("type")))
    text = str(ui.get("text") or "")
    if fn is None or not ui.get("valid", True):
        return Markdown(text, classes="component fallback") if text else None
    try:
        widget = fn(ui.get("props") or {}, text)
    except Exception:  # a renderer bug must not break the transcript
        return Markdown(text, classes="component fallback") if text else None
    widget.add_class("component")
    return widget


def _panel(body: Any, title: str, style: str = "cyan") -> Static:
    return Static(Panel(body, title=title, title_align="left", border_style=style, expand=False))


@renderer("weather")
def _weather(p: dict, text: str) -> Widget:
    head = Text.assemble((f"{p['temp_c']}°C", "bold"), " · ", p["condition"])
    if p.get("feels_like_c") is not None:
        head.append(f"  (feels like {p['feels_like_c']}°C)", style="dim")
    extras = " · ".join(
        f"{label} {p[key]}{unit}"
        for key, label, unit in (("humidity", "humidity", "%"), ("wind_kmph", "wind", " km/h"))
        if p.get(key) is not None
    )
    forecast = Table(box=None, show_header=False, padding=(0, 2))
    for day in p.get("forecast", []):
        forecast.add_row(day["date"], f"{day['min_c']}–{day['max_c']}°C")
    return _panel(Group(head, Text(extras, style="dim"), forecast), f"☁ {p['place']}")


@renderer("link_preview")
def _link(p: dict, text: str) -> Widget:
    body = Text(p.get("description") or "", style="dim") if p.get("description") else Text("")
    body.append(f"\n{p['url']}", style="underline blue")
    return _panel(body, f"🔗 {p['title']}", "blue")


@renderer("search_results")
def _search(p: dict, text: str) -> Widget:
    lines = Text()
    for i, hit in enumerate(p.get("results", []), 1):
        lines.append(f"{i}. {hit['title']}\n", style="bold")
        lines.append(f"   {hit['link']}\n", style="blue")
    return _panel(lines or Text("no results", style="dim"), f"🔎 {p['query']}", "blue")


@renderer("video_results")
def _videos(p: dict, text: str) -> Widget:
    lines = Text()
    for i, v in enumerate(p.get("results", []), 1):
        lines.append(f"{i}. {v.get('title')}", style="bold")
        lines.append(f"  {v.get('channel') or ''} {v.get('duration') or ''}\n", style="dim")
    return _panel(lines, f"▶ {p['query']}", "red")


@renderer("file")
def _file(p: dict, text: str) -> Widget:
    return Static(Text.assemble("📄 ", (p["path"], "bold"), (f"  lines {p['start']}–{p['end']} of {p['total_lines']}", "dim")))


@renderer("file_list")
def _file_list(p: dict, text: str) -> Widget:
    entries = Text("\n".join(p.get("entries", [])) or "(empty)")
    return _panel(entries, f"📁 {p['path']}/", "yellow")


@renderer("file_write")
def _file_write(p: dict, text: str) -> Widget:
    verb = "created" if p.get("created") else "saved"
    return Static(Text.assemble("✎ ", (p["path"], "bold"), f" {verb}"))


@renderer("file_delete")
def _file_delete(p: dict, text: str) -> Widget:
    return Static(Text.assemble("🗑 ", (p["path"], "bold"), " deleted"))


@renderer("diff")
def _diff(p: dict, text: str) -> Widget:
    lines = difflib.unified_diff(
        p["before"].splitlines(), p["after"].splitlines(), fromfile=p["path"], tofile=p["path"], lineterm=""
    )
    return Static(Syntax("\n".join(lines), "diff", theme="ansi_dark", background_color="default"))


@renderer("grep")
def _grep(p: dict, text: str) -> Widget:
    body = Text("\n".join(p.get("matches", [])) or "no matches", style="" if p.get("matches") else "dim")
    return _panel(body, f"🔍 {p['pattern']}", "yellow")


@renderer("choice")
def _choice(p: dict, text: str) -> Widget:
    line = Text.assemble(("? ", "bold magenta"), p["question"])
    if p.get("answer"):
        line.append(f"  → {p['answer']}", style="bold")
    elif p.get("options"):
        line.append("  [" + " / ".join(p["options"]) + "]", style="dim")
    return Static(line)


@renderer("delegation")
def _delegation(p: dict, text: str) -> Widget:
    shared = " (with context)" if p.get("shared_context") else ""
    line = Text.assemble(("↳ ", "magenta"), (p["persona"], "bold magenta"), f"{shared}: ", (p["task"], "dim"))
    if p.get("question"):
        line.append_text(Text.assemble("\n  ", ("? asks: ", "yellow"), p["question"]))
    return Static(line)


@renderer("memory_saved")
def _memory(p: dict, text: str) -> Widget:
    return Static(Text.assemble(("✓ remembered: ", "green"), p["fact"]))


@renderer("skill_loaded")
def _skill(p: dict, text: str) -> Widget:
    return Static(Text(f"⚙ skill: {p['skill']}", style="dim"))


@renderer("download")
def _download(p: dict, text: str) -> Widget:
    return Static(Text.assemble(("⬇ ", "green"), f"{p['kind']} downloaded ", (p["url"], "dim")))


class TableView(DataTable):
    """A DataTable that fills itself once mounted (DataTable needs a running app to measure)."""

    def __init__(self, columns: list[str], rows: list[list[str]]):
        super().__init__(show_cursor=False, zebra_stripes=True)
        self._columns, self._rows = columns, rows
        self.styles.height = min(len(rows) + 2, 15)

    def on_mount(self) -> None:
        self.add_columns(*self._columns)
        self.add_rows(self._rows)


@renderer("table")
def _table(p: dict, text: str) -> Widget:
    return TableView(p["columns"], p["rows"])


@renderer("chart")
def _chart(p: dict, text: str) -> Widget:
    labels, values = p.get("labels", []), p.get("values", [])
    peak = max((abs(v) for v in values), default=1) or 1
    width = max((len(str(label)) for label in labels), default=1)
    rows = Text()
    for label, value in zip(labels, values):
        bar = "█" * max(1, round(28 * abs(value) / peak))
        rows.append(f"{str(label):<{width}} ", style="bold")
        rows.append(bar, style="green")
        rows.append(f" {value:g}\n")
    return _panel(rows, f"📊 {p.get('title') or 'chart'}", "green")


@renderer("card")
def _card(p: dict, text: str) -> Widget:
    body = Text(p["body"])
    if p.get("url"):
        body.append(f"\n{p['url']}", style="underline blue")
    return _panel(body, p["title"], "magenta")
