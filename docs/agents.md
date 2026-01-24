# Agents Reference

This document provides detailed information about each agent in the Omen system, including their capabilities, tools, and use cases.

## Agent Overview

| Agent | Registry Key | Primary Role | Tools Count |
|-------|--------------|--------------|-------------|
| Triage Agent | `orc` | Orchestration & Routing | UI, Task, DateTime |
| Web Search Agent | `web` | Web Research | Search, Web, Download |
| Filesystem Agent | `fs` | File Management | Full CRUD, Grep |
| Analysis Agent | `analyst` | Data Analysis | Analysis, Automation, Code |
| Ideation Agent | `idea` | Creative Writing | Read, Write, Edit |
| Study Agent | `tutor` | Learning Assistant | DateTime |
| Resume Agent | `resume` | Resume Optimization | File operations |
| Context Memory Agent | `memory` | Memory Management | Context tools |

---

## Triage Agent (Orchestrator)

**Registry Key:** `orc`

### Purpose
The Triage Agent is the primary interface and orchestrator. It analyzes user requests, routes them to appropriate specialists, and manages complex multi-step workflows.

### Capabilities
- Request analysis and classification
- Agent routing and handoffs
- Task management for long-running work
- General conversation handling
- Workflow coordination

### Decision Workflow
1. **UNDERSTAND**: Parse user request, identify task type
2. **EVALUATE**: Check if direct answer is possible
3. **ROUTE**: Select appropriate specialist agent

### Tools
- UI Tools (display formatting)
- Task Management Tools
- `get_current_datetime`

### Subagents
- Web Search Agent
- Filesystem Agent

### When to Use
- Complex or ambiguous requests
- Multi-step workflows
- Task coordination
- General queries

---

## Web Search Agent

**Registry Key:** `web`

### Purpose
Performs web research, searches for information, scrapes web content, and downloads media.

### Capabilities
- Web search (DuckDuckGo, Searx)
- YouTube video search
- URL scraping with optional summarization
- Weather information
- Audio/video downloads
- Browser automation

### Tools
- `web_search` - Search the web using Searx
- `duckduckgo_search` - Alternative search via DuckDuckGo
- `search_youtube_videos` - Find YouTube videos
- `scrape_url` - Scrape and extract web content
- `open_url_in_browser` - Open URLs in browser
- `download_audio` - Download audio from videos
- `download_video` - Download videos
- `get_weather_info` - Weather lookups
- `get_current_datetime`

### When to Use
- Research tasks
- Finding current information
- Media downloads
- Weather queries
- URL content extraction

---

## Filesystem Agent

**Registry Key:** `fs`

### Purpose
Manages file operations within the sandbox environment, including reading, writing, editing, and organizing files.

### Capabilities
- File CRUD operations
- Directory management
- Content search (grep)
- File moving and copying

### Tools
- `list_files` - List directory contents
- `read_file` - Read file content
- `write_file` - Create/overwrite files
- `edit_file_section` - Targeted file editing
- `append_to_file` - Append content to files
- `create_directory` - Create directories
- `delete_file` - Remove files
- `delete_directory` - Remove directories
- `move_file` - Move/rename files
- `copy_file` - Copy files
- `grep_file_content` - Search within files
- `get_current_datetime`

### Sandbox Path
All file operations are restricted to the `root/` directory for security.

### When to Use
- File organization tasks
- Document creation/editing
- Content search
- Workspace management

---

## Analysis Agent

**Registry Key:** `analyst`

### Purpose
Performs data analysis, generates reports, executes code, and automates analytical workflows.

### Capabilities
- Dataset exploration and profiling
- Statistical analysis
- Correlation analysis
- Machine learning pipelines
- Report generation
- Code execution

### Tools

#### Data Analysis Tools
- `dataset_overview` - Quick dataset inspection
- `dataset_quality_report` - Missing values, cardinality, stats
- `dataset_correlation_report` - Feature correlations

#### Automation Tools
- `run_auto_eda` - Automated exploratory data analysis
- `run_auto_modeling` - Automated ML pipeline
- `run_script` - Execute Python scripts
- `execute_code` - Run Python code snippets

#### Also Includes
- Filesystem tools
- Search tools
- URL scraping

### Supported Data Formats
- CSV, TSV
- Excel (.xlsx, .xls)
- JSON, JSONL
- Parquet

### When to Use
- Data analysis tasks
- Report generation
- Code execution
- Automated ML workflows

---

## Ideation Agent

**Registry Key:** `idea`

### Purpose
Assists with creative writing, brainstorming, and content drafting.

### Capabilities
- Brainstorming ideas
- Content drafting
- Creative writing
- Document outlining

### Tools
- `read_file` - Read existing content
- `write_file` - Create new content
- `edit_file_section` - Revise content
- `append_to_file` - Add to documents
- `get_current_datetime`

### Subagents
- Web Search Agent (for research during ideation)

### When to Use
- Creative writing tasks
- Brainstorming sessions
- Content planning
- Document drafting

---

## Study Agent

**Registry Key:** `tutor`

### Purpose
Learning assistant that helps with studying topics and understanding concepts.

### Capabilities
- Concept explanation
- Study guidance
- Topic breakdowns
- Learning path suggestions

### Tools
- `get_current_datetime`

### Notes
For deep-dive analysis, the Study Agent can hand off to the Analysis Agent.

### When to Use
- Learning new topics
- Concept clarification
- Study planning
- Educational queries

---

## Resume Agent

**Registry Key:** `resume`

### Purpose
Specialized in resume optimization, reading, editing, and improving professional documents.

### Capabilities
- Resume analysis
- Content optimization
- Format improvement
- Career advice

### Tools
- File reading and editing tools

### When to Use
- Resume review
- Professional document optimization
- Career-related content

---

## Context Memory Agent

**Registry Key:** `memory`

### Purpose
Manages persistent memory storage for conversation contexts and learned information.

### Capabilities
- Save conversation contexts
- Load stored memories
- Update existing contexts
- List available memories

### Tools
- `save_context_topic` - Save or update context
- `load_context_topic` - Retrieve saved context
- `list_context_topics` - List all memories
- `update_context_content` - Modify specific content
- `delete_context_topic` - Remove memories
- `get_current_datetime`

### Storage Location
`memory_store/memories/` - Markdown files for human-readable storage

### When to Use
- Saving important information
- Retrieving past context
- Building knowledge base
- Cross-session memory

---

## Creating Custom Agents

### Directory Structure

```
my_agents/
└── custom_agent/
    ├── __init__.py
    ├── agent.py
    └── prompt.py
```

### Agent Definition (agent.py)

```python
from my_agents.base_agent import agent_config, my_agent
from config.agent_config import AGENT_CONFIGS
from .prompt import CUSTOM_AGENT_PROMPT, CUSTOM_HANDOFF_INSTRUCTIONS

config = AGENT_CONFIGS["custom_agent"]
instructions = CUSTOM_AGENT_PROMPT

custom_agent = my_agent(
    agent_name="Custom Agent",
    config=agent_config(**config),
    instructions=instructions,
    handoff_instructions=CUSTOM_HANDOFF_INSTRUCTIONS,
    tools=[...],  # Your tools here
)
```

### Prompt Definition (prompt.py)

```python
CUSTOM_AGENT_PROMPT = """
You are a specialized agent for [purpose].

## Capabilities
- [List capabilities]

## Guidelines
- [Usage guidelines]
"""

CUSTOM_HANDOFF_INSTRUCTIONS = """
### custom_agent
**Capabilities:** [Brief capability list]

**Route to this agent when users want to:**
- [Use case 1]
- [Use case 2]
"""
```

### Registration (agent_runtime.py)

```python
from my_agents import custom_agent

_AGENT_REGISTRY["custom"] = custom_agent.agent
```
