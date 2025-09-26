from typing import Literal
from openai import OpenAI
import pyaudio
import threading
import io
import time
import random
import keyboard
import markdown
from bs4 import BeautifulSoup

from openai import OpenAI
from config.agent_config import AGENT_CONFIGS
import config.agent_personality as personality

config = AGENT_CONFIGS["triage_agent"]
BASE_URL = config["BASE_URL"]
API_KEY = config["API_KEY"]
MODEL_NAME: str = config["MODEL_NAME"]
PERSONALITY, _ = personality.get_personality()

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


class TTS:
    def __init__(
        self,
        voice: str = "am_michael(1)+am_fenrir(1)+am_echo(1)",
        speed: float = 1.2,
        response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "pcm",
        base_url: str = "http://localhost:8880/v1",
        api_key: str = "not-needed",
    ):

        self.voice = voice
        self.api_key = api_key
        self.base_url = base_url
        self.response_format = response_format
        self.speed = speed
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        self._pyaudio = pyaudio.PyAudio()

        self.player = self._pyaudio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=24000,
            output=True,
        )

        # Control flags for playback
        self.is_playing = False
        self.is_paused = False
        self.stop_requested = False
        self.audio_buffer = io.BytesIO()
        self.playback_thread = None
        self.current_position = 0

    def start(self, text: str):
        """Start tts playback of the given text"""
        # Stop any existing playback
        self.stop()

        # Reset state
        self.is_playing = True
        self.is_paused = False
        self.stop_requested = False
        self.audio_buffer = io.BytesIO()
        self.current_position = 0

        # Add hotkeys for control
        keyboard.add_hotkey("ctrl+p", self.pause)
        keyboard.add_hotkey("ctrl+r", self.play)
        keyboard.add_hotkey("ctrl+s", self.stop)

        # Start playback in a new thread
        self.playback_thread = threading.Thread(
            target=self._playback_thread, args=(text,)
        )
        self.playback_thread.daemon = True
        self.playback_thread.start()

    def _playback_thread(self, text: str):
        """Worker thread to handle audio streaming and buffering"""

        # First, get the complete audio stream and store it
        with self.client.audio.speech.with_streaming_response.create(
            model="kokoro",
            voice=self.voice,
            input=text,
            response_format=self.response_format,  # type: ignore
            speed=self.speed,
        ) as response:
            for chunk in response.iter_bytes(chunk_size=1024):
                if self.stop_requested:
                    return
                self.audio_buffer.write(chunk)

        # Reset buffer position for playback
        self.audio_buffer.seek(0)
        audio_data = self.audio_buffer.getvalue()
        buffer_size = 1024

        # Play the audio
        while self.current_position < len(audio_data) and not self.stop_requested:
            if not self.is_paused:
                end_pos = min(self.current_position + buffer_size, len(audio_data))
                chunk = audio_data[self.current_position : end_pos]
                self.player.write(chunk)
                self.current_position = end_pos
            else:
                # When paused, sleep briefly to avoid CPU hogging
                time.sleep(0.1)

        # Mark as not playing when done
        if not self.stop_requested:
            self.is_playing = False

    def stop(self):
        """Stop tts playback completely"""
        if self.is_playing:
            self.stop_requested = True
            self.is_playing = False
            self.is_paused = False

            # Wait for playback thread to finish
            if self.playback_thread and self.playback_thread.is_alive():
                self.playback_thread.join(timeout=1.0)

            # Reset state
            self.current_position = 0

        try:
            keyboard.remove_hotkey("ctrl+p")
            keyboard.remove_hotkey("ctrl+r")
            keyboard.remove_hotkey("ctrl+s")
        except KeyError:
            pass

    def pause(self):
        """Pause tts playback"""
        if self.is_playing and not self.is_paused:
            self.is_paused = True

    def play(self):
        """Resume paused tts playback"""
        if self.is_playing and self.is_paused:
            self.is_paused = False

    def speak(self, text: str, user_query: str | None = None) -> str:
        """Speak the given text"""
        if len(text.strip()) > 200:
            try:
                text = summarise_response(user_query, text)
            except Exception:
                text = text[:200] + "..."
        self.start(text)
        return text

    def shutdown(self):
        """Shutdown the tts system"""
        self.stop()

        # Terminate PyAudio
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    speaker = TTS(
        voice="am_echo",
        speed=1.2,
    )
    speaker.speak("Hello, this is a test of the tts system.")

    time.sleep(5)  # Wait for a while to let the speech finish
    speaker.stop()
