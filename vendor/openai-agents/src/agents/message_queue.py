"""Omen fork: user messages sent while a run is in progress.

Pass a `MessageQueue` in `RunConfig(message_queue=...)` and call `put()` from
anywhere (UI thread, voice thread, another task). Queued messages are injected
as user input right after the current turn's tool outputs, before the next
model call. If the model produced a final answer while messages were pending,
the run continues for another turn instead of finishing.

Messages queued after the last injection point of a run stay in the queue;
the caller should check `pending()` when the run ends and start a new run.
"""

from __future__ import annotations

import threading
from collections import deque


class MessageQueue:
    def __init__(self) -> None:
        self._items: deque[str] = deque()
        self._lock = threading.Lock()

    def put(self, text: str) -> None:
        with self._lock:
            self._items.append(text)

    def pending(self) -> int:
        with self._lock:
            return len(self._items)

    def drain(self) -> list[str]:
        with self._lock:
            items = list(self._items)
            self._items.clear()
            return items

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


__all__ = ["MessageQueue"]
