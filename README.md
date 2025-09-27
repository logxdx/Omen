# Omen - AI Multi-Agent System

Omen is a sophisticated multi-agent AI system designed for intelligent task orchestration and specialized execution. The system features a hierarchical agent architecture with a central triage agent that routes requests to specialized agents, each equipped with domain-specific tools and capabilities.

## Architecture Overview

### Core Components

-   **Triage Agent (Orchestrator)**: Central routing and coordination agent that analyzes user requests and delegates to appropriate specialized agents
-   **Specialized Agents**: Domain-specific agents for web search, file operations, ideation, study, memory management, and code analysis
-   **Tool System**: Comprehensive toolkit providing filesystem operations, web interactions, memory management, code execution, and search capabilities
-   **CLI Interface**: Rich console-based interface with streaming responses and text-to-speech support
-   **Configuration System**: Flexible agent configuration with personality traits and model settings

### Agent Hierarchy

```
User Request
    ↓
Triage Agent (Routes & Coordinates)
    ↓
Specialized Agents:
├── Web Search Agent
├── Filesystem Agent
├── Ideation Agent
├── Study Agent
├── Memory Agent
└── Analysis Agent
```

## Multi-Agent Abilities

### Triage Agent

-   **Role**: Request analysis and intelligent routing
-   **Capabilities**:
    -   Complex workflow coordination
    -   Multi-agent orchestration
    -   Ambiguous request resolution
    -   Agent capability guidance
-   **Tools**: Current datetime retrieval

### Web Search Agent

-   **Role**: Information retrieval and web research
-   **Capabilities**:
    -   DuckDuckGo and Searx search
    -   YouTube video search
    -   URL scraping and content extraction
    -   Weather information retrieval
-   **Tools**: Web search, scraping, weather API

### Filesystem Agent

-   **Role**: File and directory management
-   **Capabilities**:
    -   Complete file operations (CRUD)
    -   Directory structure manipulation
    -   File content editing and searching
    -   Data organization and storage
-   **Tools**: File read/write, directory operations, content editing

### Ideation Agent

-   **Role**: Creative thinking and idea generation
-   **Capabilities**:
    -   Brainstorming and concept development
    -   Creative problem solving
    -   Innovation workflows
-   **Tools**: Memory integration, web research access

### Study Agent

-   **Role**: Learning and research assistance
-   **Capabilities**:
    -   Study material organization
    -   Research coordination
    -   Knowledge synthesis
    -   Educational content processing
-   **Tools**: File access, web search, memory systems, analysis tools

### Memory Agent

-   **Role**: Knowledge persistence and retrieval
-   **Capabilities**:
    -   Long-term memory storage
    -   Semantic search and retrieval
    -   Memory organization and management
    -   Context preservation across sessions
-   **Tools**: Memory CRUD operations, search, history tracking

### Analysis Agent

-   **Role**: Computational analysis and code execution
-   **Capabilities**:
    -   Python code execution
    -   Data analysis and visualization
    -   Debugging and troubleshooting
    -   Computational problem solving
-   **Tools**: Python interpreter, datetime utilities

## Tool System

The system provides a comprehensive toolkit organized by functionality:

### Filesystem Tools

-   `list_files`: Directory content listing
-   `read_file`: File content reading
-   `write_file`: File creation and writing
-   `create_directory`: Directory creation
-   `delete_file`: File deletion
-   `delete_directory`: Directory removal
-   `move_file`: File relocation
-   `copy_file`: File duplication
-   `edit_file_section`: Targeted content editing
-   `append_to_file`: Content appending

### Memory Tools

-   `memory_add`: Store information
-   `memory_search`: Semantic search
-   `memory_delete`: Remove memories
-   `memory_update`: Modify stored data
-   `memory_history`: Access interaction history
-   `memory_get_all`: Retrieve all memories

### Web Tools

-   `duckduckgo_search`: Privacy-focused web search
-   `searx_search`: Decentralized search
-   `search_youtube_videos`: Video content discovery
-   `open_url_in_browser`: URL launching
-   `get_weather_info`: Weather data retrieval
-   `scrape_url`: Web content extraction
-   `download_audio`: Audio file downloading
-   `download_video`: Video file downloading

### Python Tools

-   `execute_python_code`: Safe code execution environment

### Miscellaneous Tools

-   `get_current_datetime`: Current time retrieval

## Configuration System

### Agent Configuration

-   Individual model configurations for each agent
-   API key management via environment variables
-   Base URL and model name settings
-   Maximum interaction turns (15 default)

### Personality System

-   Customizable agent personalities
-   Character-consistent responses
-   Specialized system prompts per agent

### Memory Configuration

-   ChromaDB for vector storage
-   Graph-based memory relationships
-   Persistent storage across sessions

## CLI Interface

The command-line interface provides:

-   **Rich Console Output**: Formatted text with panels and markdown support
-   **Streaming Responses**: Real-time response display
-   **Text-to-Speech**: Audio output for responses
-   **Interactive Prompts**: User-friendly input handling
-   **Keyboard Controls**: Interrupt and control capabilities

## Getting Started

1. **Install uv** (if not already installed):

    ```bash
    pip install uv
    ```

2. **Setup venv & Install dependencies**:

    ```bash
    uv sync
    ```

3. **Configuration**: Set up environment variables for API keys

4. **Run**: Execute `uv run  main.py` to start the CLI interface

5. **Interact**: Begin conversations with the triage agent

## Architecture Benefits

-   **Modularity**: Specialized agents for focused tasks
-   **Scalability**: Easy addition of new agents and tools
-   **Flexibility**: Dynamic handoffs and workflow adaptation
-   **Reliability**: Isolated agent failures don't affect the system
-   **Extensibility**: Plugin-like tool and agent addition
