"""Text-to-speech engines behind one interface, and a Speaker that plays them.

An engine turns text into float32 mono audio at its own sample rate:

    engine = make_engine("kitten")      # or OMEN_TTS=...; "auto" picks the first available
    audio = engine.synthesize("Hello.")  # numpy float32, engine.sample_rate

`Speaker(engine)` plays text in a background thread, sentence by sentence (the next sentence is
synthesized while the current one plays, so speech starts after the first sentence even for
engines without streaming), with stop / pause / play for barge-in.

Each engine's package is an optional extra (`uv sync --extra tts-kitten`, …) and is imported only
when that engine is created.
"""

from __future__ import annotations

import os
import queue
import re
import threading
import time
import urllib.request
from typing import Any, Callable, Iterator, Protocol

import numpy as np

TTS_URL = os.getenv("OMEN_TTS_URL", "http://localhost:8880/v1")


class Engine(Protocol):
    name: str
    sample_rate: int

    def synthesize(self, text: str) -> np.ndarray:
        """float32 mono audio in [-1, 1] at `sample_rate`."""
        ...


def sentences(text: str, max_chars: int = 300) -> list[str]:
    """Split text into speakable chunks (sentences, long ones cut at commas or spaces)."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?;:])\s+", text) if p.strip()]
    out: list[str] = []
    for part in parts:
        while len(part) > max_chars:
            cut = part.rfind(", ", 0, max_chars)
            cut = cut + 1 if cut > 0 else part.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            out.append(part)
    return out


def to_float32(audio: Any) -> np.ndarray:
    """numpy/torch/int16 audio → flat float32 numpy in [-1, 1]."""
    if hasattr(audio, "detach"):  # torch tensor
        audio = audio.detach().cpu().float().numpy()
    audio = np.asarray(audio)
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    return np.clip(audio.astype(np.float32).reshape(-1), -1.0, 1.0)


# -- engines ------------------------------------------------------------------------------- #


class KokoroEngine:
    """Kokoro through an OpenAI-compatible speech server (e.g. Kokoro-FastAPI on :8880)."""

    name = "kokoro"
    sample_rate = 24000

    def __init__(self, voice: str | None = None, speed: float = 1.15, base_url: str = TTS_URL):
        from openai import OpenAI

        self.voice = voice or os.getenv("OMEN_TTS_VOICE") or "af_heart"
        self.speed = speed
        self.client = OpenAI(api_key="not-needed", base_url=base_url)

    def synthesize(self, text: str) -> np.ndarray:
        response = self.client.audio.speech.create(
            model="kokoro", voice=self.voice, input=text, response_format="pcm", speed=self.speed,
        )
        return to_float32(np.frombuffer(response.read(), dtype=np.int16))


ENGINES: dict[str, Callable[[], Engine]] = {"kokoro": KokoroEngine}
AUTO_ORDER = ["kokoro"]


def _kokoro_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{TTS_URL}/models", timeout=2):
            return True
    except Exception:
        return False


def make_engine(name: str | None = None) -> Engine:
    """The engine named by `name` / OMEN_TTS; "auto" (default): the first one that loads."""
    name = (name or os.getenv("OMEN_TTS") or "auto").lower()
    if name != "auto":
        if name not in ENGINES:
            raise KeyError(f"unknown TTS engine {name!r}; choose from {', '.join(ENGINES)}")
        return ENGINES[name]()
    errors = []
    for candidate in AUTO_ORDER:
        if candidate == "kokoro" and not _kokoro_reachable():
            errors.append(f"kokoro: no server at {TTS_URL}")
            continue
        try:
            return ENGINES[candidate]()
        except Exception as e:  # not installed, model download failed, …
            errors.append(f"{candidate}: {e}")
    raise RuntimeError("no TTS engine available (" + "; ".join(errors) + ")")


# -- playback ------------------------------------------------------------------------------ #


class Speaker:
    """Plays text through an engine in the background; stop / pause / play for barge-in."""

    def __init__(self, engine: Engine, output: Callable[[int], Any] | None = None):
        self.engine = engine
        self._open_output = output or _pyaudio_output
        self._stream: Any = None
        self._generation = 0  # bumped by stop(): stale threads exit
        self._paused = threading.Event()
        self._lock = threading.Lock()
        self.thread: threading.Thread | None = None

    @property
    def is_playing(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, text: str) -> None:
        self.stop()
        with self._lock:
            self._generation += 1
            generation = self._generation
        self._paused.clear()
        self.thread = threading.Thread(target=self._play, args=(text, generation), daemon=True)
        self.thread.start()

    def _live(self, generation: int) -> bool:
        return generation == self._generation

    def _play(self, text: str, generation: int) -> None:
        chunks: queue.Queue = queue.Queue(maxsize=2)

        def put(item: Any) -> bool:
            while self._live(generation):  # never block forever once stopped
                try:
                    chunks.put(item, timeout=0.1)
                    return True
                except queue.Full:
                    continue
            return False

        def produce() -> None:  # synthesize ahead while the previous sentence plays
            for sentence in sentences(text):
                try:
                    audio = self.engine.synthesize(sentence)
                except Exception:
                    break
                if not put(audio):
                    return
            put(None)

        threading.Thread(target=produce, daemon=True).start()
        if self._stream is None:
            self._stream = self._open_output(self.engine.sample_rate)
        while self._live(generation):
            try:
                audio = chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            if audio is None:
                return
            pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
            step = self.engine.sample_rate // 20  # 50 ms writes, so stop/pause react fast
            for i in range(0, len(pcm), step):
                while self._paused.is_set() and self._live(generation):
                    time.sleep(0.02)
                if not self._live(generation):
                    return
                self._stream.write(pcm[i : i + step].tobytes())

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
        self._paused.clear()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=1.0)

    def pause(self) -> None:
        if self.is_playing:
            self._paused.set()

    def play(self) -> None:
        self._paused.clear()

    def shutdown(self) -> None:
        self.stop()
        if self._stream is not None and hasattr(self._stream, "close"):
            self._stream.close()


def _pyaudio_output(sample_rate: int) -> Any:
    import pyaudio

    return pyaudio.PyAudio().open(format=pyaudio.paInt16, channels=1, rate=sample_rate, output=True)


def write_wav(path: str, audio: np.ndarray, sample_rate: int) -> None:
    """Save float32 audio as 16-bit PCM WAV (for samples and tests)."""
    import wave

    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm.tobytes())


def stream_sentences(engine: Engine, text: str) -> Iterator[np.ndarray]:
    for sentence in sentences(text):
        yield engine.synthesize(sentence)
