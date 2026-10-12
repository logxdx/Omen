"""Voice frontend: `omen voice` (speech in, speech out, the same Runtime as the TUI and web UI).

- Lazy: the speech stack (faster-whisper, pyaudio, torch, …; `uv sync --extra voice`) is imported
  only here. Without it, or without a microphone, `omen voice` falls back to the text chat; without
  a reachable TTS server, replies are printed only.
- Barge-in: starting to talk pauses speech; the utterance stops it. If Omen is still working, the
  utterance goes into the run's message queue (it steers the run instead of starting a new one).
- Questions (`ask_user`) are spoken; the next utterance answers them.
- What is spoken is clean text (no hint tags, code, tables, links or markdown); a long reply becomes
  a short spoken briefing from the side model. The full reply is always printed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import urllib.request
from typing import Any, AsyncIterator, Awaitable, Callable

from omen.core.events import TextMessageEnd, UserQuestion
from omen.ui.extract import strip_hints

logger = logging.getLogger(__name__)

SPOKEN_LIMIT = 320  # characters; longer replies are summarized for speech
TTS_URL = os.getenv("OMEN_TTS_URL", "http://localhost:8880/v1")
BRIEFING_PROMPT = (
    "The full reply is already on the user's screen. Say the gist out loud in at most 40 words: what it "
    "is and its most important numbers or facts, then say the details are on screen. "
    "Plain sentences, no lists, no URLs, no markdown. Speak as the assistant, to the user.\n"
    "Example: \"I've put a five-day Lisbon plan on screen: museums first, Sintra on day three, and it "
    "comes to about 900 euros.\""
)

Summarize = Callable[[str, str], Awaitable[str]]


def speech_text(reply: str) -> str:
    """A reply as plain sentences for text-to-speech."""
    text, _ = strip_hints(reply)
    text = re.sub(r"```.*?```", " The code is on screen. ", text, flags=re.DOTALL)
    lines, in_table = [], False
    for line in text.splitlines():
        if re.match(r"^\s*\|.*\|\s*$", line):
            if not in_table:
                lines.append("The table is on screen.")
            in_table = True
            continue
        in_table = False
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links: keep the label
    text = re.sub(r"<?https?://[^\s)>]+>?", "the link on screen", text)
    text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", text, flags=re.MULTILINE)  # list markers
    text = re.sub(r"[*_`#>~]+", "", text)  # emphasis, headings, quotes
    text = re.sub(r"\be\.g\.", "for example", text)
    text = re.sub(r"\bi\.e\.", "that is", text)
    sentences = []
    for line in (line.strip() for line in text.splitlines()):
        if line:
            sentences.append(line if line[-1] in ".!?:;" else line + ".")
    return re.sub(r"\s+", " ", " ".join(sentences)).strip()


class VoiceSession:
    """Routes utterances to a Runtime and speaks the results. Audio-free, so it is testable."""

    def __init__(
        self,
        runtime: Any,
        speak: Callable[[str], None],
        stop_speaking: Callable[[], None],
        summarize: Summarize | None = None,
        render: Callable[[Any], None] | None = None,
        say: Callable[[str], None] = print,
    ):
        self.runtime = runtime
        self.speak = speak
        self.stop_speaking = stop_speaking
        self.summarize = summarize
        self.render = render or (lambda event: None)
        self.say = say
        self.current: asyncio.Task | None = None

    async def handle(self, utterance: str) -> None:
        utterance = utterance.strip()
        if not utterance:
            return
        self.stop_speaking()  # barge-in
        self.say(f"› {utterance}")
        if self.runtime.pending_question is not None:
            self.runtime.answer(utterance)
        elif self.runtime.running:
            self.runtime.send(utterance)  # steers the current run
        else:
            self.current = asyncio.create_task(self._run(utterance))

    async def _run(self, text: str) -> None:
        reply = ""
        async for event in self.runtime.run(text):
            self.render(event)
            if isinstance(event, TextMessageEnd) and event.text.strip():
                reply = event.text
            elif isinstance(event, UserQuestion):
                options = f" Options: {', '.join(event.options)}." if event.options else ""
                self.speak(speech_text(event.question) + options)
        if reply:
            self.speak(await self.spoken(text, reply))

    async def spoken(self, request: str, reply: str) -> str:
        text = speech_text(reply)
        if len(text) > SPOKEN_LIMIT and self.summarize is not None:
            try:
                text = speech_text(await self.summarize(request, reply)) or text
            except Exception as e:  # speak the long version rather than nothing
                logger.warning("spoken briefing failed: %s", e)
        return _trim(text)

    async def run(self, utterances: AsyncIterator[str]) -> None:
        async for utterance in utterances:
            await self.handle(utterance)
        if self.current is not None:
            await self.current


def _trim(text: str, limit: int = SPOKEN_LIMIT * 2) -> str:
    """Cut overlong speech at a sentence boundary; the full reply is on screen."""
    if len(text) <= limit:
        return text
    cut = max(text.rfind(". ", 0, limit), text.rfind("! ", 0, limit), text.rfind("? ", 0, limit))
    head = text[: cut + 1] if cut > 0 else text[:limit].rsplit(" ", 1)[0] + "."
    return head + " The rest is on screen."


async def briefing(request: str, reply: str) -> str:
    """A short spoken version of a long reply (side model, thinking off for local models)."""
    import litellm

    from omen.config import extractor_model

    config = extractor_model()
    response = await litellm.acompletion(
        model=config.model, api_base=config.base_url, api_key=config.api_key, temperature=0, max_tokens=300,
        extra_body=config.extra_body or None,
        messages=[  # the instruction comes last: small models otherwise echo the reply
            {"role": "user", "content": f"The user asked: {request}\n\n<reply>\n{reply[:6000]}\n</reply>\n\n{BRIEFING_PROMPT}"},
        ],
    )
    return response.choices[0].message.content or ""


def _tts_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/models", timeout=2):
            return True
    except Exception:
        return False


async def _microphone(stt: Any, on_empty: Callable[[], None]) -> AsyncIterator[str]:
    """Utterances from the speech recognizer (it blocks, so it runs in a thread)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def listen() -> None:
        while True:
            try:
                text = stt.text()
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
                return
            loop.call_soon_threadsafe(queue.put_nowait, text or "")

    threading.Thread(target=listen, daemon=True).start()
    while True:
        item = await queue.get()
        if isinstance(item, Exception):
            raise item
        if not item.strip():
            on_empty()  # a noise woke the detector: resume speaking
            continue
        yield item


def run_voice(runtime: Any, render: Callable[[Any], None]) -> bool:
    """Run the voice loop. Returns False if voice can't start (the caller falls back to text)."""
    try:
        from omen.voice.KokoroTTS import KokoroTTS
        from omen.voice.WhisperSTT import WhisperSTT
    except ImportError as e:
        print(f"voice needs the speech packages: uv sync --extra voice ({e.name} is missing)")
        return False
    tts = None
    if _tts_reachable(TTS_URL):
        tts = KokoroTTS(base_url=TTS_URL)
    else:
        print(f"no TTS server at {TTS_URL} (OMEN_TTS_URL): replies will be printed only")
    try:
        stt = WhisperSTT(spinner=True, on_vad_detect_start=tts.pause if tts else None)
    except Exception as e:  # no microphone, no model, …
        print(f"speech recognition failed to start: {e}")
        if tts:
            tts.shutdown()
        return False

    session = VoiceSession(
        runtime,
        speak=tts.start if tts else (lambda text: None),
        stop_speaking=tts.stop if tts else (lambda: None),
        summarize=briefing,
        render=render,
    )
    print("listening… (Ctrl+C to quit)")
    try:
        asyncio.run(session.run(_microphone(stt, on_empty=tts.play if tts else (lambda: None))))
    except KeyboardInterrupt:
        pass
    finally:
        stt.shutdown()
        if tts:
            tts.shutdown()
    return True
