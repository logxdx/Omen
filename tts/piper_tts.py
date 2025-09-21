from piper import PiperVoice, SynthesisConfig
import pyaudio
import threading
import io
import time


# TTS Class with play, pause, resume, stop
class TTS:
    def __init__(
        self,
        model_path="piper_voices/en_US-libritts_r-medium.onnx",
        speaker_id: int = 26,
        speed: float = 1.0,
        volume: float = 1.2,
    ):
        self.syn_config = SynthesisConfig(
            speaker_id=speaker_id,
            length_scale=1 / speed,
            normalize_audio=True,
            volume=volume,
        )
        self.voice = PiperVoice.load(model_path)
        self._pyaudio = pyaudio.PyAudio()
        self._stream = None
        self._lock = threading.Lock()
        self._paused = threading.Event()
        self._paused.set()  # Not paused initially
        self._stopped = False
        self._thread = None

    def _start_stream(self):
        # Piper outputs 16-bit signed little-endian PCM, 22050 Hz, mono
        self._stream = self._pyaudio.open(
            format=pyaudio.paInt16, channels=1, rate=22050, output=True
        )

    def play(self, text):
        self.stop()
        self._stopped = False
        self._paused.set()
        self._start_stream()
        time.sleep(0.1)

        def _run():
            for chunk in self.voice.synthesize(text, syn_config=self.syn_config):
                self._paused.wait()  # Wait if paused
                if self._stopped:
                    break
                if self._stream:
                    self._stream.write(chunk.audio_int16_bytes)
            if self._stream:
                time.sleep(0.2)
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None

        self._thread = threading.Thread(target=_run)
        self._thread.start()

    def pause(self):
        self._paused.clear()

    def resume(self):
        self._paused.set()

    def stop(self):
        self._stopped = True
        self._paused.set()
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None

    def synthesize(self, text):
        # For API: return all audio bytes at once
        audio_bytes = io.BytesIO()
        for chunk in self.voice.synthesize(text, syn_config=self.syn_config):
            audio_bytes.write(chunk.audio_int16_bytes)
        return audio_bytes.getvalue()


if __name__ == "__main__":
    import time

    text = "A transformer is an end-to-end neural architecture that uses attention instead of recurrence or convolution to relate all tokens in an input sequence at once."

    # for i in range(50):
    for i in [(7, 1.2), (25, 1.2), (26, 1.0)]:
        print(i)
        # 7, 8, 10, 25, 26, 36
        # 7, 25, 26
        # 26 is good default
        tts = TTS(speaker_id=i[0], speed=i[1])
        tts.play(text=text)
        time.sleep(10)
        tts.stop()
