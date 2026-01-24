# Configuration Guide

This document covers all configuration options in Omen, including environment setup, agent configuration, and customization.

## Environment Setup

### Prerequisites

- Python 3.10+
- `uv` (recommended) or `pip`
- Optional: Ollama (for local models)
- Optional: CUDA-capable GPU (for faster inference)

### Installation

```bash
# Using uv (recommended)
uv sync

# Using pip
pip install -r requirements.txt
```

### API Keys Setup

Create/edit `api_keys.txt` and `.env` with your API credentials:

```env
# OpenAI-compatible API endpoints
OLLAMA_BASE_URL=http://localhost:11434/v1
CEREBRAS_BASE_URL=https://api.cerebras.ai/v1

# Per-agent API keys
TRIAGE_API_KEY=your-key
WEB_SEARCH_API_KEY=your-key
FILESYSTEM_API_KEY=your-key
IDEATION_API_KEY=your-key
STUDY_API_KEY=your-key
MEMORY_API_KEY=your-key
ANALYSIS_API_KEY=your-key
CONTEXT_API_KEY=your-key
RESUME_API_KEY=your-key
GOOGLE_WORKSPACE_API_KEY=your-key
```

### Google Credentials (Optional)

For Google Workspace integration, place `credentials.json` in the project root with OAuth2 credentials from Google Cloud Console.

---

## Agent Configuration

Location: `config/agent_config.py`

### Global Settings

```python
# Maximum turns per agent interaction
MAX_TURNS = 20

# Local vs Cloud mode
LOCAL = True  # Set to False for cloud APIs
```

### Local Mode Configuration

When `LOCAL = True`, agents use Ollama or similar local inference:

```python
LOCAL_MODEL = "qwen3:1.7b"

LOCAL_CONFIG = {
    "PERSONALITY": "jarvis",
    "triage_agent": {
        "BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "API_KEY": os.getenv("TRIAGE_API_KEY"),
        "MODEL_NAME": f"openai/{LOCAL_MODEL}",
    },
    # ... other agents
}
```

### Online Mode Configuration

When `LOCAL = False`, agents use cloud APIs:

```python
ONLINE_CONFIG = {
    "PERSONALITY": "jarvis",
    "triage_agent": {
        "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
        "API_KEY": os.getenv("TRIAGE_API_KEY"),
        "MODEL_NAME": "openai/qwen-3-235b-a22b-instruct-2507",
    },
    # ... other agents
}
```

### Per-Agent Model Selection

Each agent can use a different model for optimization:

| Agent | Recommended Model Type | Use Case |
|-------|----------------------|----------|
| Triage | Large, capable | Complex routing decisions |
| Web Search | Medium, fast | Quick search tasks |
| Filesystem | Small, fast | Simple file operations |
| Analysis | Large, capable | Complex data analysis |
| Ideation | Creative model | Content generation |

### Adding New Agent Configuration

```python
ONLINE_CONFIG = {
    # ... existing configs
    "my_new_agent": {
        "BASE_URL": os.getenv("MY_API_BASE_URL"),
        "API_KEY": os.getenv("MY_API_KEY"),
        "MODEL_NAME": "openai/my-model",
    },
}
```

---

## UI Configuration

Location: `config/ui_config.py`

### Version

```python
Version = "1.4.0"
```

### Runtime Settings

```python
# Conversation history storage
CONVERSATION_HISTORY: list[TResponseInputItem] = []

# Voice mode settings
SKIP_TURN: bool = False
QUIT_SESSION: bool = False

# Interaction modes
HEIRARCHY_MODE: str = "managerial"  # or "collaborative"
INTERACTION_MODE: str = "text"       # or "voice"
USE_CONTEXT_MANAGER: bool = False
```

### Theme Configuration

The Rich console theme for CLI styling:

```python
AGENT_THEME = Theme({
    # General
    "info": "cyan",
    "warning": "yellow",
    "error": "bright_red bold",
    "success": "green",
    "dim": "dim",
    "muted": "grey50",
    "border": "grey35",
    "highlight": "bold cyan",
    "accent": "magenta",
    "accent.bold": "bold magenta",
    "title": "bold white",
    
    # Roles
    "user": "bright_blue bold",
    "assistant": "bright_white",
    
    # Tools
    "tool": "bright_magenta bold",
})
```

---

## Personality Configuration

Location: `config/agent_personality.py`

Customize the assistant's personality and tone:

```python
def get_personality() -> tuple[str, str]:
    """Returns (name, personality_prompt)"""
    return "Jarvis", JARVIS_PERSONALITY

JARVIS_PERSONALITY = """
You are Jarvis, a sophisticated AI assistant...
"""
```

### Available Personalities

- `jarvis` - Professional, efficient butler-style assistant

### Creating Custom Personalities

```python
MY_PERSONALITY = """
You are [Name], a [description]...

## Tone
- [Characteristic 1]
- [Characteristic 2]

## Behavior
- [Behavior guideline]
"""
```

---

## Voice Configuration

### Speech-to-Text (STT)

Location: `stt/WhisperSTT.py`

```python
# Model settings
INIT_MODEL_TRANSCRIPTION = "base.en"
INIT_MODEL_TRANSCRIPTION_REALTIME = "tiny.en"

# Voice Activity Detection
INIT_SILERO_SENSITIVITY = 0.5
INIT_POST_SPEECH_SILENCE_DURATION = 0.5
INIT_MIN_LENGTH_OF_RECORDING = 1.0
INIT_MIN_GAP_BETWEEN_RECORDINGS = 1.0

# Wake word settings
INIT_WAKE_WORDS_SENSITIVITY = 0.5
INIT_WAKE_WORD_ACTIVATION_DELAY = 0.0
INIT_WAKE_WORD_TIMEOUT = 5.0

# Audio settings
SAMPLE_RATE = 16000
BUFFER_SIZE = 512
```

### Text-to-Speech (TTS)

Location: `tts/KokoroTTS.py`

TTS uses the configured `tts_summarizer` model to create spoken responses.

---

## Storage Configuration

### Memory Store

```
memory_store/
└── memories/           # Persistent context files (.md)
```

### Task Store

```
task_store/
└── tasks/             # Task persistence files (.json)
```

### Sandbox (Root)

```
root/
├── files/             # User workspace files
├── downloads/
│   ├── audio/         # Downloaded audio
│   └── video/         # Downloaded video
└── analysis_outputs/  # Generated reports
```

---

## Model Configuration Examples

### Using Ollama Locally

```python
LOCAL_CONFIG = {
    "triage_agent": {
        "BASE_URL": "http://localhost:11434/v1",
        "API_KEY": "ollama",
        "MODEL_NAME": "openai/llama3.1:8b",
    },
}
```

### Using OpenAI

```python
ONLINE_CONFIG = {
    "triage_agent": {
        "BASE_URL": "https://api.openai.com/v1",
        "API_KEY": os.getenv("OPENAI_API_KEY"),
        "MODEL_NAME": "gpt-4-turbo",
    },
}
```

### Using Azure OpenAI

```python
ONLINE_CONFIG = {
    "triage_agent": {
        "BASE_URL": "https://YOUR_RESOURCE.openai.azure.com/",
        "API_KEY": os.getenv("AZURE_API_KEY"),
        "MODEL_NAME": "azure/gpt-4",
    },
}
```

### Using Anthropic

```python
ONLINE_CONFIG = {
    "triage_agent": {
        "BASE_URL": "https://api.anthropic.com/v1",
        "API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "MODEL_NAME": "anthropic/claude-3-opus",
    },
}
```

---

## Troubleshooting

### Common Issues

**API Connection Errors**
- Verify `BASE_URL` is correct
- Check API key validity
- Ensure network connectivity

**Model Not Found**
- For Ollama: `ollama pull model-name`
- For cloud: Verify model name spelling

**Voice Mode Issues**
- Check PyAudio installation
- Verify microphone permissions
- Test with `python -m pyaudio`

**Memory/Storage Errors**
- Ensure write permissions for `memory_store/` and `task_store/`
- Check disk space

### Debug Mode

Enable tracing for debugging:

```python
# In cli/v1.py
from agents import set_tracing_disabled
set_tracing_disabled(disabled=False)  # Enable tracing
```
