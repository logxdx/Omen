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
import numpy as np

from openai import OpenAI
from config.agent_config import AGENT_CONFIGS, WORD_BUFFER_SIZE
import config.agent_personality as personality

config = AGENT_CONFIGS["memory_agent"]
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


def summarise_response(query: str | None, response_text: str):
    """
    Summarise the response text using OpenAI API.
    """
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    instructions = f"{selected_personality}\n\n You are the only point of contact of the user with the agent. You are to communicate with the user. Given the final response (and optionally the user query too), talk to the user about it in very brief like an assistant to their boss. You do not need to explain every detail, just the key points. Use simple language and avoid technical jargon (no need for code snippets, urls, etc). If the response is already very short, you can say it as is. Make sure the response is in plaintext with no emojis, artifacts (URLs, etc) or shortforms (e.g. -> example, i.e. -> that is)."

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
    instructions = f"{selected_personality}\n\n You are the only point of contact of the user with the agent. You are to communicate with the user. Given the final response (and optionally the user query too), talk to the user about it in very brief like an assistant to their boss. You do not need to explain every detail, just the key points. Use simple language and avoid technical jargon (no need for code snippets, urls, etc). If the response is already very short, you can say it as is. Make sure the response is in plaintext with no emojis, artifacts (URLs, etc) or shortforms (e.g. -> example, i.e. -> that is)."

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
            stream=True,
        )
        for chunk in output:
            if text := chunk.choices[0].delta.content:
                yield text
    except Exception as e:
        output = "The output is on your screen."  # Fallback to original response if error occurs
        yield output


class KokoroTTS:
    """
    Text to Speech class using OpenAI API and PyAudio for playback
    """

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

        try:
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
        except Exception as e:

            return

        # Reset buffer position for playback
        self.audio_buffer.seek(0)
        audio_data = self.audio_buffer.getvalue()
        buffer_size = 1024

        try:
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
        except Exception as e:
            pass

        # Mark as not playing when done
        if not self.stop_requested:
            self.is_playing = False

    def _stream_playback_thread(self, text_iterator):
        """Worker thread to handle streaming text to TTS"""
        word_buffer = []

        try:
            for chunk in text_iterator:
                if self.stop_requested:
                    return
                if not chunk:
                    continue

                # Split chunk into words and add to buffer
                words = chunk.split(" ")
                word_buffer.extend(words)

                # Send to TTS when we have enough words
                # if len(word_buffer) >= WORD_BUFFER_SIZE:
                if (
                    str(word_buffer[-1]).endswith((".", "!", "?", "\n"))
                    and len(word_buffer) > WORD_BUFFER_SIZE
                ):
                    buffer_text = " ".join(word_buffer)
                    with self.client.audio.speech.with_streaming_response.create(
                        model="kokoro",
                        voice=self.voice,
                        input=buffer_text,
                        response_format=self.response_format,  # type: ignore
                        speed=self.speed,
                    ) as tts_response:
                        for audio_chunk in tts_response.iter_bytes(chunk_size=1024):
                            if self.stop_requested:
                                return
                            if not self.is_paused:
                                self.player.write(audio_chunk)
                            else:
                                # When paused, sleep briefly to avoid CPU hogging
                                time.sleep(0.1)
                    word_buffer = []  # Clear buffer after processing

            # Process any remaining words in buffer
            if word_buffer and not self.stop_requested:
                buffer_text = " ".join(word_buffer)
                with self.client.audio.speech.with_streaming_response.create(
                    model="kokoro",
                    voice=self.voice,
                    input=buffer_text,
                    response_format=self.response_format,  # type: ignore
                    speed=self.speed,
                ) as tts_response:
                    for audio_chunk in tts_response.iter_bytes(chunk_size=1024):
                        if self.stop_requested:
                            return
                        if not self.is_paused:
                            self.player.write(audio_chunk)
                        else:
                            time.sleep(0.1)
        except Exception as e:
            pass

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

    def speak(self, text: str, user_query: str | None = None):
        """Speak the given text"""
        # Stop any existing playback
        self.stop()

        if len(text.strip()) > 200:
            text = summarise_response(user_query, text)

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

    def stream_speak(self, text: str, user_query: str | None = None):
        """Speak text from an iterator, buffering words for reduced latency"""
        # Stop any existing playback
        self.stop()

        if len(text.strip()) > 200:
            text_iterator = stream_summarised_response(user_query, text)
        else:
            text_iterator = iter(text.split(". "))

        # Reset state
        self.is_playing = True
        self.is_paused = False
        self.stop_requested = False

        # Add hotkeys for control
        keyboard.add_hotkey("ctrl+p", self.pause)
        keyboard.add_hotkey("ctrl+r", self.play)
        keyboard.add_hotkey("ctrl+s", self.stop)

        # Start streaming playback in a new thread
        self.playback_thread = threading.Thread(
            target=self._stream_playback_thread, args=(text_iterator,)
        )
        self.playback_thread.daemon = True
        self.playback_thread.start()

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

    speaker = KokoroTTS(
        # voice="am_echo",
        speed=1.5,
    )
    text = """
We need to produce an explanation of transformer architecture. Probably want to explain the concepts: self-attention, multi-head attention, encoders and decoders; then architecture: embedding, positional encoding, multi-head attention, feed-forward, residual connections, layernorm, etc. Might also explain multi-head self-attention, key, query, value. Then architecture for transformer encoder, decoder. Provide a high-level algorithm as well-known. Might mention huggingface code snippets or apply usage in natural. The user didn't specify level, so likely a general explanation from conceptual to details. We'll produce a thorough explanation including diagrams and pseudocode. Should not mention code? It's okay to provide sample code implementation of the transformer. Let's combine both conceptual and code.

We'll produce comprehensive explanation. Also important to escalate: start with history, high-level architecture: The transformer architecture is built from
self-attention blocks. Provide details. Provide equations for scaling by sqrt(d_k). Provide the mathematics. Provide the novelty difference between LSTM and
self-attention; advantages, e.g., parallelization.

We'll mention mechanism: multi-head attention. Provide expected embed dimension d_model. Provide dropout. Provide the architecture needing scaling. Provide the
generation of representation representation. Also mention feed-forward network.

We'll mention usage in different tasks: autoregressive like GPT, encoder-decoder like BERT, etc. Provide summarizing.

Also mention variants: BERT, GPT, BART, etc.

Also include some demonstration code in python using PyTorch functions that implement transformer block or replicate.

Also include part about training details: weight initialization, layer normalization, the use of dropout.

Ok let's produce. We'll produce accordingly.
"""
    # spoken = speaker.speak(text=text)
    # time.sleep(30)  # Wait for a while to let the speech finish
    spoken_stream = speaker.stream_speak(text=text)
    time.sleep(60)  # Wait for a while to let the speech finish
    speaker.stop()
