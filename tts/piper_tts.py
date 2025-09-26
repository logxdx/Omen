from piper import PiperVoice, SynthesisConfig
import pyaudio
import threading
import io
import time
import keyboard
import pathlib
import random
import markdown
from bs4 import BeautifulSoup

from openai import OpenAI
from config.agent_config import AGENT_CONFIGS
import config.agent_personality as personality

config = AGENT_CONFIGS["triage_agent"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME: str = config["MODEL_NAME"]
PERSONALITY: str = str(config.get("PERSONALITY", "random")).upper()

# Select personality based on config
if PERSONALITY == "RANDOM":
    selected_personality = random.choice(personality.PERSONALITIES)
else:
    selected_personality = personality.PERSONALITY_DICT[PERSONALITY]


# Convert Markdown to plain text using BeautifulSoup
def markdown_to_plaintext(md_text):
    # Convert Markdown to HTML
    html_content = markdown.markdown(md_text)
    # Remove HTML tags to get plain text
    soup = BeautifulSoup(html_content, "html.parser")
    plaintext = soup.get_text()
    return plaintext


def summarise_response(query: str | None, response_text: str) -> str:
    """
    Summarise the response text using OpenAI API.
    """
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    instructions = f"{selected_personality}\n\n You are the only point of contact of the user with the agent. You are to communicate with the user. Given the final response (and optionally the user query too), talk to the user about it in very brief like an assistant to their boss. You do not need to explain every detail, just the key points. Use simple language and avoid technical jargon. If the response is already very short, you can say it as is. Make sure the response is in plaintext with no emojis, artifacts (URLs, etc) or shortforms (e.g. -> example, i.e. -> that is)."
    try:
        output = str(
            client.chat.completions.create(
                model=MODEL_NAME.lstrip("openai/"),
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
            .choices[0]
            .message.content
        )
    except Exception as e:
        print(f"Error during summarization: {e}")
        output = "The output is on your screen."  # Fallback to original response if error occurs

    return markdown_to_plaintext(output)


# Path to the model directory
MODEL_DIR = pathlib.Path(__file__).parent / "piper_voices"


class TTS:
    def __init__(
        self,
        model_path=MODEL_DIR / "en_US-libritts_r-medium.onnx",
        speaker_id: int = 7,
        speed: float = 1.2,
        volume: float = 1.25,
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
        buffer_size = 1024

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
                time.sleep(0.1)

        # Mark as not playing when done (but keep stream alive)
        if not self.stop_requested:
            self.is_playing = False

    def speak(self, text, user_query: str | None = None):
        """Start TTS playback of the given text"""
        # Stop any existing playback (but keep stream alive)
        self._stop_playback_only()

        text = summarise_response(user_query, text)

        # Reset state
        self.is_playing = True
        self.is_paused = False
        self.stop_requested = False
        self.audio_buffer = io.BytesIO()
        self.current_position = 0

        # Ensure stream is ready (but don't recreate if already exists)
        self._start_stream()

        # Add hotkeys for control
        keyboard.add_hotkey("ctrl+p", self.pause)
        keyboard.add_hotkey("ctrl+r", self.resume)
        keyboard.add_hotkey("ctrl+s", self.stop)

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

        # Remove hotkeys
        try:
            keyboard.remove_hotkey("ctrl+p")
            keyboard.remove_hotkey("ctrl+r")
            keyboard.remove_hotkey("ctrl+s")
        except KeyError:
            pass

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

    def synthesize(self, text):
        # For API: return all audio bytes at once
        audio_bytes = io.BytesIO()
        for chunk in self.voice.synthesize(text, syn_config=self.syn_config):
            audio_bytes.write(chunk.audio_int16_bytes)
        return audio_bytes.getvalue()


if __name__ == "__main__":
    import time

    text = "A transformer is an end-to-end neural architecture that uses attention instead of recurrence or convolution to relate all tokens in an input sequence at once."

    for i in [(7, 1.2), (25, 1.2), (26, 1.2)]:
        # for i in [(26, 1.2)]:
        print(i)
        # 7, 8, 10, 25, 26, 36
        # 7, 25, 26
        # 26 is good default
        tts = TTS(speaker_id=i[0], speed=i[1])
        out = tts.speak(text=text)
        print(out)
        time.sleep(10)
        tts.stop()
