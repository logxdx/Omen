# Omen Documentation

Welcome to the official documentation for **Omen** - a sophisticated multi-agent AI system with voice capabilities, advanced memory management, and an extensible tool ecosystem.

## 📚 Documentation Index

| Document | Description |
|----------|-------------|
| [Architecture Overview](architecture.md) | System design, agent orchestration, and data flow |
| [Agents Reference](agents.md) | Detailed documentation for all agents and their capabilities |
| [Tools Reference](tools.md) | Complete list of available tools and their usage |
| [Configuration Guide](configuration.md) | Setup, environment variables, and customization options |
| [CLI Guide](cli.md) | Command-line interface commands and interaction modes |
| [Voice System](voice.md) | Speech-to-Text (STT) and Text-to-Speech (TTS) integration |
| [Task Management](task_management.md) | Long-running task tracking and persistence |

## 🚀 Quick Start

```bash
# Clone and install
git clone <repository-url>
cd omen
uv sync  # or: pip install -r requirements.txt

# Configure API keys
# Edit api_keys.txt and credentials.json

# Run
python main.py
```

## 🏗️ Project Structure

```
omen/
├── main.py                 # Application entry point
├── agent_runtime.py        # Agent orchestration and handoff wiring
├── cli/                    # Command-line interface implementation
├── config/                 # Agent, UI, and personality configuration
├── docs/                   # Documentation (you are here)
├── memory_store/           # Persistent memory storage
├── my_agents/              # Agent definitions
│   ├── base_agent.py       # Base agent class and utilities
│   ├── triage_agent/       # Orchestrator agent
│   ├── web_search_agent/   # Web research agent
│   ├── filesystem_agent/   # File management agent
│   ├── analysis_agent/     # Data analysis agent
│   ├── ideation_agent/     # Creative writing agent
│   ├── study_agent/        # Learning assistant agent
│   ├── resume_agent/       # Resume optimization agent
│   └── context_memory_agent/ # Memory management agent
├── tools/                  # Tool implementations
├── stt/                    # Speech-to-Text modules
├── tts/                    # Text-to-Speech modules
├── task_store/             # Task persistence storage
└── root/                   # Sandbox for file operations
```

## 🔑 Key Features

- **Multi-Agent Architecture**: Specialized agents orchestrated by a central triage agent
- **Voice Interface**: Whisper STT + Kokoro/Piper TTS for natural conversation
- **Persistent Memory**: File-based context storage with semantic search
- **Rich Tool Ecosystem**: Web, filesystem, data analysis, and automation tools
- **Task Management**: Track and resume long-running multi-step tasks
- **Flexible Deployment**: Support for both local (Ollama) and cloud LLMs

## 📖 Version

Current Version: **1.4.0**

---

*For detailed information on any topic, please refer to the linked documentation pages.*
