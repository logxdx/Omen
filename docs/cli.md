# CLI Guide

This document covers the command-line interface (CLI) for interacting with Omen.

## Starting the CLI

```bash
python main.py
```

This launches the interactive CLI with the welcome panel showing available commands.

## Commands Reference

| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/h` | Show help and available commands |
| `/quit` | `/q`, `/exit` | Exit the session |
| `/clear` | `/cls` | Clear the screen |
| `/agent` | `/a` | List or switch agents |
| `/mode` | `/m` | Select interaction mode (text/voice) |
| `/hierarchy` | `/hier` | Select hierarchy mode |
| `/context` | `/ctx` | Toggle context manager |
| `/history` | `/hist` | View conversation history |
| `/reset` | | Reset conversation |

---

## Detailed Command Usage

### `/agent` - Agent Management

**List all agents:**
```
/agent
```

Displays a table of available agents with their registry keys.

**Switch to a specific agent:**
```
/agent web
/agent analyst
/agent fs
```

This bypasses the triage agent and interacts directly with the specified agent.

**Available Agent Keys:**
| Key | Agent |
|-----|-------|
| `orc` | Triage (Orchestrator) |
| `web` | Web Search |
| `fs` | Filesystem |
| `idea` | Ideation |
| `tutor` | Study |
| `analyst` | Analysis |
| `resume` | Resume |
| `memory` | Context Memory |

---

### `/mode` - Interaction Mode

```
/mode
```

Prompts to select between:

1. **Text Mode** (default) - Standard keyboard input/output
2. **Voice Mode** - Speech-to-text input, text-to-speech output

Voice mode requires:
- Working microphone
- PyAudio properly configured
- Whisper model downloaded

---

### `/hierarchy` - Hierarchy Mode

```
/hierarchy
```

Prompts to select between:

1. **Collaborative Mode** - Agents can handoff directly to each other
2. **Managerial Mode** (default) - Triage agent manages all interactions

**Collaborative Flow:**
```
User → Triage → Web Search → Filesystem → User
```

**Managerial Flow:**
```
User → Triage → [Web Search] → Triage → [Filesystem] → Triage → User
```

---

### `/context` - Context Manager

```
/context
```

Toggles the context memory agent:

1. **Enabled** - Conversations are saved to memory for future reference
2. **Disabled** (default) - No automatic memory saving

---

### `/history` - View History

```
/history
```

Displays the current conversation history in a formatted view.

---

### `/reset` - Reset Session

```
/reset
```

Clears the conversation history and resets the session state.

---

### `/clear` - Clear Screen

```
/clear
/cls
```

Clears the terminal and re-displays the welcome panel.

---

### `/quit` - Exit

```
/quit
/q
/exit
```

Gracefully exits the CLI session.

---

## Conversation Flow

### Basic Interaction

```
You: What's the weather in Tokyo?

🌐 Web Search Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The current weather in Tokyo is 22°C with partly cloudy skies...
```

### Multi-Turn Conversation

```
You: Search for recent AI news

🌐 Web Search Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Here are the latest AI news articles...

You: Save that to a file called ai_news.md

📁 Filesystem Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Successfully wrote to ai_news.md
```

### Direct Agent Interaction

```
You: /agent analyst
Switched to: Analysis Agent

You: Analyze the dataset at data.csv
```

---

## Voice Mode Usage

### Starting Voice Mode

```
/mode
# Select option 2
```

### Voice Interaction

1. **Wake Word** (optional): Say the configured wake word to start listening
2. **Speak**: The system records your speech
3. **Processing**: Whisper transcribes your audio
4. **Response**: Agent responds with text and audio

### Voice Mode Controls

- **Automatic VAD**: Recording starts/stops based on speech detection
- **Pause TTS**: Speaking while TTS is playing will pause it
- **Wake Word**: Configurable wake word detection

---

## Output Formatting

The CLI uses Rich for formatted output:

### Agent Responses

```
┌─ Agent Name ─────────────────────────────────────────────────┐
│                                                              │
│  Response content with **markdown** support                  │
│                                                              │
│  - Bullet points                                             │
│  - Code blocks                                               │
│  - Tables                                                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Tool Calls

```
🔧 Tool: web_search
   Query: "AI news 2024"
```

### Errors

```
❌ Error: Connection failed
   Details: Unable to reach the API endpoint
```

---

## Tips and Best Practices

### Effective Queries

**Good:**
```
Search for Python async programming tutorials and save the top 3 to a file
```

**Better:**
```
1. Search for "Python async programming tutorials"
2. Summarize the top 3 results
3. Save to root/files/python_async_tutorials.md
```

### Using Tasks for Complex Work

```
Create a research task about machine learning fundamentals with steps:
1. Search for introductory resources
2. Compile key concepts
3. Create a study guide
```

### File Operations

Always specify paths relative to the sandbox:
```
Write to files/notes.md
Read the file at research/report.md
```

### Switching Context

When changing topics:
```
/reset
```
Or explicitly:
```
Let's start a new topic. I want to discuss...
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+C` | Interrupt current operation |
| `Ctrl+D` | Exit (same as `/quit`) |
| `↑/↓` | Navigate command history |
| `Tab` | Command completion (where supported) |

---

## Troubleshooting CLI Issues

### "Agent not found"

Verify the agent key with `/agent` to list available agents.

### Voice mode not starting

1. Check microphone permissions
2. Verify PyAudio installation: `pip install pyaudio`
3. Test microphone separately

### Slow responses

1. Check network connection
2. Consider using local models for faster inference
3. Reduce `MAX_TURNS` in configuration

### Display issues

1. Ensure terminal supports ANSI colors
2. Check terminal width (150 chars recommended)
3. Use a modern terminal emulator
