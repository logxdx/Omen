# Voice System

This document covers the speech-to-text (STT) and text-to-speech (TTS) capabilities in Omen.

## Overview

Omen supports full voice interaction through:

- **STT**: Whisper-based transcription (faster-whisper)
- **TTS**: Kokoro/Piper text-to-speech synthesis
- **VAD**: Voice Activity Detection (Silero)
- **Wake Words**: OpenWakeWord for activation

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Microphone │────▶│     VAD     │────▶│   Whisper   │
│    Input    │     │   (Silero)  │     │     STT     │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │    Agent    │
                                        │  Processing │
                                        └──────┬──────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Speaker   │◀────│   Kokoro    │◀────│  Response   │
│   Output    │     │     TTS     │     │ Summarizer  │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## Speech-to-Text (STT)

Location: `stt/WhisperSTT.py`

### Features

- **Fast Transcription**: Uses faster-whisper for optimized inference
- **Voice Activity Detection**: Automatic recording start/stop
- **Wake Word Detection**: Trigger recording with spoken words
- **Real-time Feedback**: Visual indicators during recording
- **GPU Acceleration**: CUDA support for faster processing

### Model Configuration

```python
# Primary transcription model
INIT_MODEL_TRANSCRIPTION = "base.en"

# Real-time processing model (lighter)
INIT_MODEL_TRANSCRIPTION_REALTIME = "tiny.en"
```

### Available Whisper Models

| Model | Parameters | English-only | Multilingual | Speed |
|-------|------------|--------------|--------------|-------|
| `tiny` | 39M | ✓ | ✓ | Fastest |
| `base` | 74M | ✓ | ✓ | Fast |
| `small` | 244M | ✓ | ✓ | Medium |
| `medium` | 769M | ✓ | ✓ | Slower |
| `large` | 1550M | ✗ | ✓ | Slowest |

### Voice Activity Detection Settings

```python
# Sensitivity (0.0 - 1.0, higher = more sensitive)
INIT_SILERO_SENSITIVITY = 0.5

# Silence duration to stop recording (seconds)
INIT_POST_SPEECH_SILENCE_DURATION = 0.5

# Minimum recording length (seconds)
INIT_MIN_LENGTH_OF_RECORDING = 1.0

# Gap between recordings (seconds)
INIT_MIN_GAP_BETWEEN_RECORDINGS = 1.0
```

### Wake Word Configuration

```python
# Wake word sensitivity (0.0 - 1.0)
INIT_WAKE_WORDS_SENSITIVITY = 0.5

# Delay before activation (seconds)
INIT_WAKE_WORD_ACTIVATION_DELAY = 0.0

# Timeout after wake word (seconds)
INIT_WAKE_WORD_TIMEOUT = 5.0

# Buffer duration (seconds)
INIT_WAKE_WORD_BUFFER_DURATION = 0.5
```

### Audio Settings

```python
SAMPLE_RATE = 16000      # Hz
BUFFER_SIZE = 512        # samples
```

### Usage Example

```python
from stt.WhisperSTT import WhisperSTT

# Initialize STT
stt = WhisperSTT(
    spinner=True,  # Show visual feedback
    on_vad_detect_start=lambda: tts.pause()  # Pause TTS on speech
)

# Start listening
text = stt.listen()
print(f"You said: {text}")
```

### Model Paths

Models are stored in:
```
stt/models/
├── whisper/      # Whisper models
├── oww/          # OpenWakeWord models
└── silero/       # Silero VAD models
```

---

## Text-to-Speech (TTS)

Location: `tts/KokoroTTS.py`

### Features

- **Response Summarization**: Condenses long responses for speech
- **Markdown Stripping**: Converts markdown to plain text
- **Streaming Support**: Real-time speech generation
- **Pause/Resume**: Interrupt speech on user input

### Response Summarization

Long agent responses are summarized before speech synthesis:

```python
def summarise_response(query: str | None, response_text: str):
    """
    Summarizes response for verbal delivery using LLM.
    
    Guidelines:
    - Focus on key points and takeaways
    - Omit technical jargon and code
    - Expand abbreviations (e.g. → for example)
    - Professional executive tone
    """
```

### Usage Example

```python
from tts.KokoroTTS import KokoroTTS

# Initialize TTS
tts = KokoroTTS()

# Speak text
tts.speak("Hello, how can I help you today?")

# Speak with summarization
tts.speak_response(
    query="What's the weather?",
    response="The current weather in Tokyo is..."
)

# Pause/Resume
tts.pause()
tts.resume()
```

### Markdown to Plaintext

```python
from tts.KokoroTTS import markdown_to_plaintext

# Convert markdown
plain = markdown_to_plaintext("**Bold** and *italic* text")
# Result: "Bold and italic text"
```

---

## Alternative TTS: Piper

Location: `tts/PiperTTS.py`

Piper provides offline, fast TTS synthesis.

### Voice Models

Voices are stored in:
```
tts/piper_voices/
```

### Available Voices

Download voices from the Piper releases page and place in the voices directory.

---

## Enabling Voice Mode

### In CLI

```
/mode
# Select option 2 (Voice)
```

### Programmatic

```python
from cli.v1 import setup_voice_mode
import config.ui_config as ui_config

# Setup voice components
setup_voice_mode()

# Enable voice mode
ui_config.INTERACTION_MODE = "voice"
```

---

## Voice Mode Flow

### Standard Flow

1. **Wait for Input**: System waits for speech
2. **VAD Detection**: Silero detects voice activity
3. **Recording**: Audio captured until silence
4. **Transcription**: Whisper converts to text
5. **Processing**: Agent processes the query
6. **Summarization**: Long responses condensed
7. **Speech**: TTS speaks the response

### Wake Word Flow

1. **Listening**: Passive wake word detection
2. **Activation**: Wake word detected
3. **Recording**: Full speech capture begins
4. **Continue**: Standard flow continues

### Interruption Handling

When the user starts speaking while TTS is active:
1. VAD detects new speech
2. TTS is paused (`tts.pause()`)
3. New recording begins
4. TTS resumes after response if needed

---

## Hardware Requirements

### Minimum

- Microphone with decent quality
- Speakers or headphones
- CPU-only inference (slower)

### Recommended

- Quality USB microphone
- CUDA-capable GPU (for faster inference)
- 8GB+ VRAM for larger models

---

## Troubleshooting

### No Audio Input

```bash
# Test PyAudio
python -c "import pyaudio; print(pyaudio.PyAudio().get_device_count())"
```

1. Check microphone permissions
2. Verify correct input device selected
3. Test microphone in other applications

### Transcription Errors

1. Use larger Whisper model (`small` or `medium`)
2. Reduce background noise
3. Speak more clearly
4. Adjust VAD sensitivity

### TTS Not Working

1. Check audio output device
2. Verify TTS model is downloaded
3. Check speaker/headphone connection

### Slow Performance

1. Use GPU acceleration if available
2. Use smaller models (`tiny` or `base`)
3. Reduce real-time processing requirements

### Wake Word Not Detecting

1. Adjust `INIT_WAKE_WORDS_SENSITIVITY`
2. Verify wake word model is loaded
3. Speak wake word clearly and consistently

---

## Configuration Summary

### STT Settings (WhisperSTT.py)

| Setting | Default | Description |
|---------|---------|-------------|
| `INIT_MODEL_TRANSCRIPTION` | `"base.en"` | Main transcription model |
| `INIT_SILERO_SENSITIVITY` | `0.5` | VAD sensitivity |
| `INIT_POST_SPEECH_SILENCE_DURATION` | `0.5` | Silence to stop recording |
| `INIT_MIN_LENGTH_OF_RECORDING` | `1.0` | Minimum recording length |
| `INIT_WAKE_WORDS_SENSITIVITY` | `0.5` | Wake word sensitivity |

### TTS Settings (KokoroTTS.py)

| Setting | Source | Description |
|---------|--------|-------------|
| `MODEL_NAME` | `agent_config["tts_summarizer"]` | LLM for summarization |
| `BASE_URL` | `agent_config["tts_summarizer"]` | API endpoint |

---

## Advanced Usage

### Custom VAD Callback

```python
def on_speech_start():
    print("Speech detected!")
    tts.pause()

stt = WhisperSTT(
    on_vad_detect_start=on_speech_start
)
```

### Streaming TTS

```python
from tts.KokoroTTS import stream_summarised_response

# Stream response generation
for chunk in stream_summarised_response(query, response):
    # Process chunks as they arrive
    pass
```

### Custom Wake Words

Add custom wake word models to `stt/models/oww/` and configure in the STT initialization.
