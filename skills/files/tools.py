"""Files skill: sandboxed file tools with plain-text output and confirmation for destructive ops."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agents import RunContextWrapper

from omen.core.ask import confirm
from omen.core.tools import ToolResult, tool

from . import filesystem as fs

MAX_GREP_MATCHES = 40


def _resolve(path: str) -> Path:
    """Sandbox path for `path`, refusing anything that resolves outside the sandbox."""
    full = (fs.SANDBOX_PATH / path.strip().lstrip("/")).resolve()
    if not fs._inside_sandbox(full):
        raise fs.AccessDeniedError(f"'{path}' is outside the sandbox")
    return full


def _rel(full: Path) -> str:
    return full.relative_to(fs.SANDBOX_PATH).as_posix() or "."


def _squash(text: str) -> str:
    """Lowercase letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


@tool
def list_files(path: str = ".") -> ToolResult:
    """List files and folders (folders end with /).

    Args:
        path: Folder to list, relative to the sandbox. Default: the sandbox root.
    """
    full = _resolve(path)
    if not full.exists():
        return ToolResult(f"'{path}' does not exist yet. write_file creates missing folders automatically.")
    if not full.is_dir():
        raise NotADirectoryError(f"'{path}' is a file, not a folder")
    entries = sorted(full.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    names = [p.name + ("/" if p.is_dir() else "") for p in entries]
    listing = "\n".join(names) if names else "(empty)"
    return ToolResult(
        f"{_rel(full)}/\n{listing}",
        details={"type": "file_list", "path": _rel(full), "entries": names},
    )


@tool(max_chars=6000)
def read_file(path: str, offset: int = 1, limit: int = 200) -> ToolResult:
    """Read a text file. Long files are returned in parts; use offset to continue.

    Args:
        path: File path relative to the sandbox.
        offset: First line to read (1 = start).
        limit: Number of lines to read.
    """
    full = _resolve(path)
    if not full.is_file():
        raise FileNotFoundError(f"'{path}' does not exist")
    lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(offset, 1)
    chunk = lines[start - 1 : start - 1 + max(limit, 1)]
    end = start + len(chunk) - 1
    header = f"{_rel(full)} (lines {start}-{end} of {len(lines)})" if lines else f"{_rel(full)} (empty)"
    more = f"\n[more: read_file(path='{path}', offset={end + 1})]" if end < len(lines) else ""
    return ToolResult(
        f"{header}\n{chr(10).join(chunk)}{more}",
        details={"type": "file", "path": _rel(full), "start": start, "end": end, "total_lines": len(lines)},
    )


@tool
async def write_file(ctx: RunContextWrapper[Any], path: str, content: str) -> ToolResult:
    """Create a file, or replace a whole file (asks the user before replacing).

    Args:
        path: File path relative to the sandbox.
        content: The complete file content.
    """
    full = _resolve(path)
    existed = full.exists()
    if existed and not await confirm(ctx, f"Replace the existing file {_rel(full)}?"):
        return ToolResult(f"Not written: the user did not confirm replacing {_rel(full)}.")
    fs.write_file_in_sandbox(_rel(full), content)
    verb = "Replaced" if existed else "Created"
    return ToolResult(
        f"{verb} {_rel(full)} ({len(content)} characters).",
        details={"type": "file_write", "path": _rel(full), "created": not existed},
    )


@tool
def append_to_file(path: str, content: str) -> ToolResult:
    """Add text to the end of a file (creates it if missing).

    Args:
        path: File path relative to the sandbox.
        content: Text to add. Include a newline at the start if needed.
    """
    full = _resolve(path)
    fs.append_to_file_in_sandbox(_rel(full), content)
    return ToolResult(f"Appended {len(content)} characters to {_rel(full)}.", details={"type": "file_write", "path": _rel(full)})


@tool
def edit_file(path: str, old_text: str, new_text: str) -> ToolResult:
    """Replace one exact piece of text in a file. Copy old_text exactly from read_file output.

    Args:
        path: File path relative to the sandbox.
        old_text: Text to replace; must appear exactly once in the file.
        new_text: Replacement text.
    """
    full = _resolve(path)
    if not full.is_file():
        raise FileNotFoundError(f"'{path}' does not exist")
    content = full.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count == 0:
        return ToolResult(
            f"Error: old_text was not found in {_rel(full)}. Read the file and copy the text exactly.",
            error="invalid_args",
        )
    if count > 1:
        return ToolResult(
            f"Error: old_text appears {count} times in {_rel(full)}. Include more surrounding text so it is unique.",
            error="invalid_args",
        )
    full.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return ToolResult(
        f"Edited {_rel(full)}.",
        details={"type": "diff", "path": _rel(full), "before": old_text, "after": new_text},
    )


@tool
def grep(pattern: str, path: str = ".") -> ToolResult:
    """Find lines containing a word or phrase, in one file or all files under a folder.

    Args:
        pattern: Text to look for (case-insensitive). Regular expressions also work.
        path: File or folder relative to the sandbox. Default: everything.
    """
    full = _resolve(path)
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)
    loose = _squash(pattern)  # "wifi" also finds "Wi-Fi"
    files = [full] if full.is_file() else sorted(p for p in full.rglob("*") if p.is_file())
    matches = []
    for file in files:
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(lines, 1):
            if regex.search(line) or (loose and loose in _squash(line)):
                matches.append(f"{_rel(file)}:{number}: {line.strip()[:200]}")
                if len(matches) >= MAX_GREP_MATCHES:
                    break
        if len(matches) >= MAX_GREP_MATCHES:
            break
    if not matches:
        return ToolResult(f"No lines match '{pattern}'.", details={"type": "grep", "pattern": pattern, "matches": []})
    more = f"\n[stopped at {MAX_GREP_MATCHES} matches]" if len(matches) >= MAX_GREP_MATCHES else ""
    return ToolResult("\n".join(matches) + more, details={"type": "grep", "pattern": pattern, "matches": matches})


@tool
async def delete_file(ctx: RunContextWrapper[Any], path: str) -> ToolResult:
    """Delete a file (asks the user first).

    Args:
        path: File path relative to the sandbox.
    """
    full = _resolve(path)
    if not full.is_file():
        raise FileNotFoundError(f"'{path}' does not exist or is a folder")
    if not await confirm(ctx, f"Delete {_rel(full)}?"):
        return ToolResult(f"Not deleted: the user did not confirm deleting {_rel(full)}.")
    fs.delete_file_in_sandbox(_rel(full))
    return ToolResult(f"Deleted {_rel(full)}.", details={"type": "file_delete", "path": _rel(full)})


TOOLS = [list_files, read_file, write_file, append_to_file, edit_file, grep, delete_file]
