"""Test doubles."""

from __future__ import annotations

import asyncio
import copy
import json

from omen.core.llm import Completion, TextDelta, ToolCall

HANG = object()  # a turn that never produces a token


class FakeLLM:
    """Replays scripted turns.

    Each turn is either a string (the answer, streamed word by word), a list of
    `(tool_name, args)` tool calls, an Exception to raise, or HANG.
    """

    def __init__(self, turns, delay: float = 0.0):
        self.turns = list(turns)
        self.delay = delay
        self.requests: list[dict] = []

    async def stream(self, messages, tools):
        self.requests.append({
            "messages": copy.deepcopy(messages),
            "tools": [t["function"]["name"] for t in tools],
        })
        turn = self.turns.pop(0)
        if turn is HANG:
            await asyncio.sleep(60)
        if isinstance(turn, Exception):
            raise turn
        if isinstance(turn, str):
            for i, word in enumerate(turn.split(" ")):
                if self.delay:
                    await asyncio.sleep(self.delay)
                yield TextDelta(word if i == 0 else " " + word)
            yield Completion(text=turn)
            return
        calls = [
            ToolCall(id=f"call_{len(self.requests)}_{i}", name=name,
                     arguments=args if isinstance(args, str) else json.dumps(args))
            for i, (name, args) in enumerate(turn)
        ]
        yield Completion(tool_calls=calls)
