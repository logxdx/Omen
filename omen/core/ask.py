"""Asking the user: the `ask_user` core tool and `confirm()` for tools that need permission."""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper

from omen.core.tools import ToolResult, tool

YES = {"y", "yes", "ok", "okay", "sure", "confirm", "go ahead", "do it", "yep", "yeah"}


async def ask(ctx: RunContextWrapper[Any], question: str, options: list[str] | None = None) -> str:
    """Ask through the frontend (OmenContext.ask); raises if no user can answer."""
    asker = getattr(ctx.context, "ask", None)
    if asker is None:
        raise RuntimeError("no user is available to answer")
    return (await asker(question, options)).strip()


async def confirm(ctx: RunContextWrapper[Any], question: str) -> bool:
    """Yes/no confirmation for destructive actions. Anything but a clear yes is a no."""
    try:
        answer = await ask(ctx, question, ["yes", "no"])
    except RuntimeError:
        return False
    return answer.lower().rstrip(".!") in YES


@tool
async def ask_user(ctx: RunContextWrapper[Any], question: str, options: list[str] | None = None) -> ToolResult:
    """Ask the user a question and wait for the answer. Use it for choices you can't make yourself.

    Args:
        question: The question, short and specific.
        options: Optional list of answers to choose from.
    """
    try:
        answer = await ask(ctx, question, options)
    except RuntimeError as e:
        return ToolResult(f"Error: could not ask the user: {e}.", error="exception")
    return ToolResult(
        f"The user answered: {answer}",
        details={"type": "choice", "question": question, "options": options, "answer": answer},
    )
