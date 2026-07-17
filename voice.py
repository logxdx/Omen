"""Thin wrapper over the existing stt/ and tts/ pipelines.

Instantiated lazily on the first /voice toggle so text-only sessions
never pay the model-loading cost.
"""

from stt.WhisperSTT import WhisperSTT
from tts.KokoroTTS import KokoroTTS


class Voice:
    def __init__(self):
        self.tts = KokoroTTS()
        self.stt = WhisperSTT(
            spinner=True,
            on_vad_detect_start=lambda: self.tts.pause(),
        )

    def listen(self) -> str:
        """Block until speech is captured, return the transcription."""
        return self.stt.text()

    def speak(self, text: str, user_query: str | None = None) -> None:
        self.tts.speak(text, user_query=user_query)

    def shutdown(self) -> None:
        self.tts.shutdown()
        self.stt.shutdown()
