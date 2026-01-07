# AI Agent System

A sophisticated, multi-agent AI system designed to handle complex tasks through a collaborative architecture. This system integrates voice capabilities, advanced memory management, and a wide array of tools to assist with research, coding, data analysis, and daily automation.

## 🌟 Key Features

*   **Multi-Agent Architecture**: A specialized team of agents orchestrated by a central Triage Agent to handle diverse tasks efficiently.
*   **Voice Interface**: Full support for voice interaction using Whisper (STT) and Kokoro/Piper (TTS) for a natural conversational experience.
*   **Advanced Memory**:
    *   **Vector Store**: Semantic search capabilities using ChromaDB.
    *   **Graph Store**: Knowledge graph for relationship mapping.
    *   **File-based Memory**: Persistent storage of research and context.
*   **Rich Tool Ecosystem**: Integrated tools for web searching, file manipulation, data analysis, Google Workspace automation, and more.
*   **Interactive CLI**: A polished command-line interface built with `rich` for structured output and easy interaction.

## 🤖 Agents

The system is composed of several specialized agents:

| Agent | Role | Key Capabilities |
|-------|------|------------------|
| **Triage (Orchestrator)** | Primary Interface | Routes user requests to the appropriate specialist agent. Handles general queries and manages the conversation flow. |
| **Web Search** | Researcher | Performs web searches (Google, DuckDuckGo), scrapes content, and finds YouTube videos. |
| **Filesystem** | File Manager | Reads, writes, edits, and organizes files within the workspace. |
| **Analysis** | Data Scientist | Performs data analysis, generates reports, executes code, and automates workflows. |
| **Google Workspace** | Assistant | Manages Calendar events and Gmail (reading/drafting emails). |
| **Ideation** | Creative Writer | Brainstorms ideas, drafts content, and helps with creative writing tasks. |
| **Study** | Tutor | Assists with learning and studying topics (hands off to Analysis for deep dives). |
| **Resume** | Career Coach | Specialized in reading, editing, and optimizing resumes. |

## 🛠️ Tools & Capabilities

The agents have access to a powerful suite of tools:

*   **Web**: Search engines, URL scraping, browser automation, media downloading (audio/video).
*   **Filesystem**: Full CRUD operations on files and directories.
*   **Data Analysis**: Automated EDA reports, correlation analysis, and modeling workflows.
*   **Automation**: Code execution and script running.
*   **Google Integration**: Calendar and Gmail API access.
*   **Context Manager**: Tools to save, load, and manage conversation context.

## 🚀 Getting Started

### Prerequisites

*   Python 3.10+
*   `uv` (recommended for dependency management) or `pip`

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd ai
    ```

2.  **Install dependencies:**
    Using `uv`:
    ```bash
    uv sync
    ```
    Or using `pip`:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuration:**
    *   Ensure `api_keys.txt` and `credentials.json` are properly set up in the root directory for external API access (OpenAI, Google, etc.).
    *   Check `config/` for agent and UI configuration options.

### Usage

Start the system by running the main script:

```bash
python main.py
```

## 📂 Project Structure

```
.
├── agent_runtime.py    # Core logic for agent orchestration and handoffs
├── main.py             # Entry point of the application
├── cli/                # Command-line interface implementation
├── config/             # Configuration files for agents and UI
├── memory_store/       # Storage for vector, graph, and file memories
├── my_agents/          # Definitions and logic for each specific agent
├── stt/                # Speech-to-Text modules (Whisper, Parakeet)
├── tts/                # Text-to-Speech modules (Kokoro, Piper)
└── tools/              # Tool implementations (Web, Data, FS, etc.)
```

## 🧠 Memory System

The system uses a hybrid memory approach:
*   **`memory_store/memories/`**: Markdown files for human-readable long-term storage.

## 🎙️ Voice Mode

The system supports hands-free interaction:
*   **STT**: Uses `WhisperSTT` for accurate speech recognition.
*   **TTS**: Uses `KokoroTTS` or `PiperTTS` for natural-sounding speech synthesis.
*   **Activation**: Voice mode can be toggled within the CLI.
