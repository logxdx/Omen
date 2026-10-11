"""HTTP server: AG-UI over SSE for the web UI (and any AG-UI client).

    python -m omen serve            # http://127.0.0.1:8765

POST /agent                       AG-UI RunAgentInput → SSE stream of AG-UI events.
                                  forwardedProps.omen: {"persona": "writer", "components": ["weather", ...]}
POST /threads/{id}/messages       {"text"} queue a message into the running agent
POST /threads/{id}/answer         {"text"} answer the pending question (ACTIVITY_SNAPSHOT "question")
POST /threads/{id}/abort          stop the current run
GET  /threads                     saved threads (newest first)
GET  /threads/{id}                the thread's messages + UI payloads, for re-rendering history
GET  /ui/schema                   JSON Schema of every UI component (TypeScript generation)
GET  /health
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from omen.agui import AgUiMapper
from omen.assistant import Assistant, build_assistant
from omen.config import SESSIONS_DIR
from omen.core import Runtime, Session
from omen.ui.components import json_schema
from omen.ui.extract import Extractor, components_for
from omen.ui.history import history

_THREAD_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TextBody(BaseModel):
    text: str


@dataclass
class Thread:
    id: str
    session: Session
    runtime: Runtime
    assistant: Assistant


def create_app(
    *,
    sessions_dir: Path = SESSIONS_DIR,
    assistant_factory: Callable[..., Assistant] = build_assistant,
    extractor: Extractor | None = None,
) -> FastAPI:
    app = FastAPI(title="Omen", version="0.1")
    threads: dict[str, Thread] = {}
    extractor = extractor if extractor is not None else Extractor()

    async def build_components(text: str, ui: set[str] | None):
        return await components_for(text, extractor, ui)

    def thread(thread_id: str, persona: str | None = None) -> Thread:
        if not _THREAD_ID.match(thread_id):
            raise HTTPException(400, "invalid thread id")
        current = threads.get(thread_id)
        if current is None:
            session = Session(sessions_dir / f"{thread_id}.jsonl", session_id=thread_id)
            assistant = assistant_factory(persona=persona)
            runtime = Runtime.for_assistant(assistant, session, components=build_components)
            current = threads[thread_id] = Thread(thread_id, session, runtime, assistant)
        elif persona and persona != current.assistant.persona.name and not current.runtime.running:
            current.assistant = current.assistant.switch(persona)
            current.runtime.attach(current.assistant)
        return current

    def existing(thread_id: str) -> Thread:
        if thread_id not in threads:
            raise HTTPException(404, "no such thread")
        return threads[thread_id]

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/ui/schema")
    async def ui_schema() -> dict:
        return json_schema()

    @app.post("/agent")
    async def agent(body: RunAgentInput) -> StreamingResponse:
        omen_props = (body.forwarded_props or {}).get("omen", {}) if isinstance(body.forwarded_props, dict) else {}
        try:
            t = thread(body.thread_id, omen_props.get("persona"))
        except KeyError:
            raise HTTPException(400, f"unknown persona {omen_props.get('persona')!r}")
        if t.runtime.running:
            raise HTTPException(409, "a run is already in progress; POST /threads/{id}/messages to add to it")
        text = _last_user_text(body.messages)
        if not text:
            raise HTTPException(400, "no user message")
        components = omen_props.get("components")
        t.runtime.ui = set(components) if isinstance(components, list) else None
        encoder = EventEncoder()

        async def stream() -> AsyncIterator[str]:
            mapper = AgUiMapper(body.thread_id, body.run_id)
            async for event in t.runtime.run(text):
                for agui_event in mapper.map(event):
                    yield encoder.encode(agui_event)

        return StreamingResponse(stream(), media_type=encoder.get_content_type())

    @app.post("/threads/{thread_id}/messages")
    async def send(thread_id: str, body: TextBody) -> dict:
        t = existing(thread_id)
        if not t.runtime.running:
            raise HTTPException(409, "no run in progress; start one with POST /agent")
        t.runtime.send(body.text)
        return {"queued": True}

    @app.post("/threads/{thread_id}/answer")
    async def answer(thread_id: str, body: TextBody) -> dict:
        if not existing(thread_id).runtime.answer(body.text):
            raise HTTPException(409, "no question is waiting for an answer")
        return {"answered": True}

    @app.post("/threads/{thread_id}/abort")
    async def abort(thread_id: str) -> dict:
        existing(thread_id).runtime.abort()
        return {"aborted": True}

    @app.get("/threads")
    async def list_threads() -> list[dict]:
        files = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"id": f.stem, "updated": f.stat().st_mtime, "active": f.stem in threads} for f in files]

    @app.get("/threads/{thread_id}")
    async def get_thread(thread_id: str) -> dict:
        if not _THREAD_ID.match(thread_id):
            raise HTTPException(400, "invalid thread id")
        session = threads[thread_id].session if thread_id in threads else Session(sessions_dir / f"{thread_id}.jsonl")
        if not session.entries:
            raise HTTPException(404, "no such thread")
        return {"id": thread_id, "messages": history(session)}

    return app


def _last_user_text(messages: list[Any]) -> str:
    for message in reversed(messages or []):
        if getattr(message, "role", None) != "user":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content.strip()
        parts = [getattr(p, "text", "") for p in content or [] if getattr(p, "type", "") == "text"]
        return "\n".join(p for p in parts if p).strip()
    return ""


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    serve()
