from typing import Literal
import pyaudio
import threading
import io
import time
import random
import keyboard
import markdown
from openai import OpenAI

from config.agent_config import AGENT_CONFIGS, WORD_BUFFER_SIZE
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
    instructions = f"{selected_personality}\n\n You are the direct assistant to the the user (your Boss). Given the final response (and optionally the user query too), repeat it in very brief like an assistant briefing their boss. You do not need to explain every detail, just the key points. Use simple language and avoid technical jargon (no need for code snippets, urls, etc). For tables, explain them briefly, bringing up important points. If the response is already very short, you can say it as is. Make sure the response is in plaintext with no emojis, artifacts (URLs, etc). Always expand shortforms (e.g. -> example, i.e. -> that is). Talk in first person and have a professional tone."

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
            max_tokens=4000,
        )
        output = str(output.choices[0].message.content)
        return markdown_to_plaintext(output)
    except Exception as e:
        output = "The output is on your screen."  # Fallback to original response if error occurs

    return markdown_to_plaintext(output)


def stream_summarised_response(query: str | None, response_text: str):
    """
    Summarise the response text using OpenAI API.
    """
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    instructions = f"{selected_personality}\n\n You are the direct assistant to the the user (your Boss). Given the final response (and optionally the user query too), repeat it in very brief like an assistant briefing their boss. You do not need to explain every detail, just the key points. Use simple language and avoid technical jargon (no need for code snippets, urls, etc). For tables, explain them briefly, bringing up important points. If the response is already very short, you can say it as is. Make sure the response is in plaintext with no emojis, artifacts (URLs, etc). Always expand shortforms (e.g. -> example, i.e. -> that is). Talk in first person and have a professional tone."

    try:
        output = client.chat.completions.create(
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
            max_tokens=4000,
            stream=True,
        )
        for chunk in output:
            text = chunk.choices[0].delta.content
            yield markdown_to_plaintext(text) if text else text
        yield "<END>"
    except Exception:
        output = "The output is on your screen."  # Fallback to original response if error occurs
        yield output


class KokoroTTS:
    """
    Text to Speech class using OpenAI API and PyAudio for playback
    """

    def __init__(
        self,
        voice: str = "af_kore(1)+af_nicole(0.5)",
        speed: float = 1.0,
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

        self._spoken_text = ""

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
        self.playback_thread = None

    def start(self, text: str):
        """Start tts playback of the given text"""
        # Stop any existing playback
        self.stop()

        # Reset state
        self.is_playing = True
        self.is_paused = False
        self.stop_requested = False

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

        try:
            # First, get the complete audio stream and store it
            with self.client.audio.speech.with_streaming_response.create(
                model="kokoro",
                voice=self.voice,
                input="_  _  " + text,
                response_format=self.response_format,  # type: ignore
                speed=self.speed,
            ) as response:
                for chunk in response.iter_bytes(chunk_size=1024):
                    if self.stop_requested:
                        return
                    while self.is_paused:
                        time.sleep(0.01)
                    self.player.write(chunk)
        except Exception:
            return

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

    def speak(self, text: str, user_query: str | None = None):
        """Speak the given text"""
        # Stop any existing playback
        self.stop()

        if len(text.strip()) > 200:
            text = summarise_response(user_query, text)

        self._spoken_text = text

        # Reset state
        self.is_playing = True
        self.is_paused = False
        self.stop_requested = False

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

    @property
    def text(self):
        return self._spoken_text

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

    voice1 = "af_nicole(0.5)"
    plus = "+"
    voice2 = "af_kore(1)"
    voice = voice1 + plus + voice2
    speaker = KokoroTTS(
        voice=voice,
        speed=1.2,
    )
    text = """
I am going to fly tomorrow using my self made jetpack. Hello IST. Hi.
"""

    print(markdown_to_plaintext(text))

    # for i in stream_summarised_response(query="", response_text=text):
    #     print(i, end="")

    # text = "Hello World! I am Friday. How can I help you today?"

    spoken = speaker.speak(text=text)
    time.sleep(10)
    print(speaker.text)
    time.sleep(5)

    speaker.stop()
