from piper import PiperVoice, SynthesisConfig
import pyaudio
import threading
import io
import time
import random
import pathlib
import markdown
from openai import OpenAI

from config.agent_config import AGENT_CONFIGS
import config.agent_personality as personality

config = AGENT_CONFIGS["tts_summarizer"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME: str = config["MODEL_NAME"]
PERSONALITY, _ = personality.get_personality()


# Select personality based on config
if PERSONALITY == "RANDOM":
    selected_personality = random.choice(personality.PERSONALITIES)
else:
    selected_personality = personality.PERSONALITY_DICT[PERSONALITY]


# unmarkdown the text
def unmark_element(element, stream=None):
    if stream is None:
        stream = io.StringIO()
    if element.text:
        stream.write(element.text)
    for sub in element:
        unmark_element(sub, stream)
    if element.tail:
        stream.write(element.tail)
    return stream.getvalue()


# patch markdown for plain text output
markdown.Markdown.output_formats["plain"] = unmark_element  # type: ignore
converter = markdown.Markdown(output_format="plain")  # type: ignore
converter.stripTopLevelTags = False


# Convert Markdown to plain text
def markdown_to_plaintext(md_text):
    return converter.convert(md_text)


def summarise_response(query: str | None, response_text: str):
    """
    Summarise the response text using OpenAI API.
    """
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    instructions = f"{selected_personality}\n\n You are the only point of communication with the user. Given the final response (and optionally the user query too), talk to the user about it in very brief like an assistant to their boss. You do not need to explain every detail, just the key points. Use simple language and avoid technical jargon (no need for code snippets, urls, etc). For tables, talk about them briefly, bringing up important points, if any. If the response is already very short, you can say it as is. Make sure the response is in plaintext with no bullet points, headers, emojis, artifacts (URLs, etc). Expand shortforms (e.g. -> example, i.e. -> that is) so that it is spoken normally."

    try:
        output = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": instructions,
                },
                {
                    "role": "user",
                    "content": f"QUERY: {query}\n\nRESPONSE: {response_text}",
                },
            ],
        )
        output = str(output.choices[0].message.content)
        return markdown_to_plaintext(output)
    except Exception as e:
        output = "The output is on your screen."  # Fallback to original response if error occurs

    return markdown_to_plaintext(output)


# Path to the model directory
MODEL_DIR = pathlib.Path(__file__).parent / "piper_voices"


class PiperTTS:
    def __init__(
        self,
        model_name="glados",
        speaker_id: int | None = None,
        speed: float = 1.3,
        volume: float = 1.2,
    ):

        model_path = MODEL_DIR / model_name / f"{model_name}.onnx"
        self._spoken_text = ""
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

        # Control flags for playback
        self.is_playing = False
        self.is_paused = False
        self.stop_requested = False
        self.audio_buffer = io.BytesIO()
        self.playback_thread = None
        self.current_position = 0

        # Initialize stream once
        self._start_stream()

    def _start_stream(self):
        if self._stream is None:
            # Piper outputs 16-bit signed little-endian PCM, 22050 Hz, mono
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16, channels=1, rate=22050, output=True
            )

    def _playback_thread(self, text):
        """Worker thread to handle audio streaming and buffering"""

        # First, synthesize all audio and store it in buffer
        for chunk in self.voice.synthesize(text, syn_config=self.syn_config):
            if self.stop_requested:
                return
            self.audio_buffer.write(chunk.audio_int16_bytes)

        # Reset buffer position for playback
        self.audio_buffer.seek(0)
        audio_data = self.audio_buffer.getvalue()
        buffer_size = 2048

        # Play the audio
        while self.current_position < len(audio_data) and not self.stop_requested:
            if not self.is_paused:
                end_pos = min(self.current_position + buffer_size, len(audio_data))
                chunk = audio_data[self.current_position : end_pos]
                if self._stream:
                    self._stream.write(chunk)
                self.current_position = end_pos
            else:
                # When paused, sleep briefly to avoid CPU hogging
                time.sleep(0.01)

        # Mark as not playing when done (but keep stream alive)
        if not self.stop_requested:
            self.is_playing = False

    def speak(self, text, user_query: str | None = None):
        """Start TTS playback of the given text"""
        # Stop any existing playback (but keep stream alive)
        self._stop_playback_only()

        if len(text) > 200:
            text = summarise_response(user_query, text)

        self._spoken_text = text

        # Reset state
        self.is_playing = True
        self.is_paused = False
        self.stop_requested = False
        self.audio_buffer = io.BytesIO()
        self.current_position = 0

        # Ensure stream is ready (but don't recreate if already exists)
        self._start_stream()

        # Start playback in a new thread
        self.playback_thread = threading.Thread(
            target=self._playback_thread, args=(text,)
        )
        self.playback_thread.daemon = True
        self.playback_thread.start()

        return text  # Return the (possibly summarized) text being spoken

    def _stop_playback_only(self):
        """Stop only the playback, keep stream alive"""
        if self.is_playing:
            self.stop_requested = True
            self.is_playing = False
            self.is_paused = False

            # Wait for playback thread to finish
            if self.playback_thread and self.playback_thread.is_alive():
                self.playback_thread.join(timeout=1.0)

            # Reset state
            self.current_position = 0

    def stop(self):
        """Stop TTS playback completely (but keep stream alive for next use)"""
        self._stop_playback_only()

    def pause(self):
        """Pause TTS playback"""
        if self.is_playing and not self.is_paused:
            self.is_paused = True

    def resume(self):
        """Resume paused TTS playback"""
        if self.is_playing and self.is_paused:
            self.is_paused = False

    def shutdown(self):
        """Shutdown the TTS system and close all streams"""
        # Stop any playback first
        self._stop_playback_only()

        # Close the stream
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # Terminate PyAudio
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass

    @property
    def text(self):
        return self._spoken_text

    def synthesize(self, text):
        # For API: return all audio bytes at once
        audio_bytes = io.BytesIO()
        for chunk in self.voice.synthesize(text, syn_config=self.syn_config):
            audio_bytes.write(chunk.audio_int16_bytes)
        return audio_bytes.getvalue()

    def replay(self):
        """Replay the last spoken text"""
        if self._spoken_text:
            self.speak(self._spoken_text)


if __name__ == "__main__":
    import time

    text = "A transformer is an end-to-end neural architecture."

    tts = PiperTTS(model_name="kristin", speed=1.25, volume=1.0)
    out = tts.speak(text=text)
    print(out)
    time.sleep(5)
    tts.stop()

    # for i in [(7, 1.5), (25, 1.5), (26, 1.5)]:
    #     # for i in [(26, 1.2)]:
    #     print(i)
    #     # 7, 8, 10, 25, 26, 36
    #     # 7, 25, 26
    #     # 26 is good default
    #     tts = PiperTTS(speaker_id=i[0], speed=i[1])
    #     out = tts.speak(text=text)
    #     print(out)
    #     time.sleep(10)
    #     tts.stop()
