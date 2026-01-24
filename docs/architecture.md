# Architecture Overview

This document describes the high-level architecture of Omen, including its multi-agent system, orchestration patterns, and data flow.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                            │
│                    (CLI / Voice / ChatKit)                       │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT RUNTIME LAYER                          │
│                    (agent_runtime.py)                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              TRIAGE AGENT (Orchestrator)                │    │
│  │    - Request Analysis    - Agent Routing                │    │
│  │    - Task Management     - Workflow Coordination        │    │
│  └──────────────┬──────────────────────────────────────────┘    │
│                 │                                                │
│     ┌───────────┼───────────┬───────────┬───────────┐           │
│     ▼           ▼           ▼           ▼           ▼           │
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐         │
│ │  Web   │ │  File  │ │Analysis│ │Ideation│ │ Study  │ ...     │
│ │ Search │ │ System │ │ Agent  │ │ Agent  │ │ Agent  │         │
│ └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘         │
└──────┼──────────┼──────────┼──────────┼──────────┼──────────────┘
       │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────┐
│                        TOOLS LAYER                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │  Web    │ │  File   │ │  Data   │ │ Search  │ │  Task   │   │
│  │  Tools  │ │  Tools  │ │  Tools  │ │  Tools  │ │  Tools  │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────────────────────────────┘
       │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     STORAGE LAYER                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Memory Store   │  │   Task Store    │  │   Root (Sandbox)│  │
│  │  (memories/)    │  │   (tasks/)      │  │   (files/)      │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Agent Communication Patterns

### Handoffs vs Agent-as-Tools

Omen supports two distinct patterns for agent communication:

#### 1. Handoffs (Control Transfer)

```python
# Transfers COMPLETE conversation history to the new agent
# New agent takes over the conversation entirely
# Original agent loses control

# Example: Triage → Web Search Agent
# Web Search agent receives full context and continues conversation
```

**Use Cases:**
- Task requires full conversation context
- Agent specialization needed
- User should interact directly with specialist

#### 2. Agent-as-Tools (Task Delegation)

```python
# Executes a specific task and returns ONLY the final answer
# Original agent stays in control
# Sub-agent doesn't see full history

# Example: Ideation Agent calls Web Search as tool
# Gets research summary, continues its own workflow
```

**Use Cases:**
- Need specialized result without losing control
- Composing results from multiple sources
- Maintaining conversation continuity

### Hierarchy Modes

#### Collaborative Mode
Agents can handoff directly to each other, creating a peer-to-peer network.

```
User → Triage → Web Search → Filesystem → User
```

#### Managerial Mode
Triage agent manages all interactions, acting as a central coordinator.

```
User → Triage → [Web Search] → Triage → [Filesystem] → Triage → User
```

## Agent Registry

The agent registry is managed in `agent_runtime.py`:

```python
AGENT_REGISTRY = {
    "orc": triage_agent,      # Orchestrator
    "web": web_search_agent,  # Web Research
    "fs": filesystem_agent,   # File Management
    "idea": ideation_agent,   # Creative Writing
    "tutor": study_agent,     # Learning Assistant
    "analyst": analysis_agent,# Data Analysis
    "resume": resume_agent,   # Resume Optimization
    "memory": context_agent,  # Memory Management
}
```

## Data Flow

### Request Processing Flow

1. **User Input** → CLI receives text or voice input
2. **Voice Processing** (optional) → STT converts speech to text
3. **Triage Analysis** → Orchestrator analyzes request
4. **Agent Selection** → Appropriate agent(s) selected
5. **Tool Execution** → Agent uses tools to fulfill request
6. **Response Generation** → Agent formulates response
7. **Voice Output** (optional) → TTS converts response to speech
8. **User Output** → Response displayed/spoken to user

### Memory Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent     │────▶│   Memory    │────▶│  File Store │
│  Context    │     │   Tools     │     │ (memories/) │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Semantic  │
                    │   Search    │
                    └─────────────┘
```

### Task Persistence Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent     │────▶│    Task     │────▶│   JSON      │
│  Request    │     │   Manager   │     │   Store     │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       │                   ▼
       │            ┌─────────────┐
       └───────────▶│   Resume    │
                    │   on Start  │
                    └─────────────┘
```

## Model Configuration

Omen supports both local and cloud-based LLM deployment:

### Local Mode (Ollama)

```python
LOCAL_CONFIG = {
    "BASE_URL": "http://localhost:11434/v1",
    "MODEL_NAME": "openai/qwen3:1.7b",
}
```

### Online Mode (Cloud APIs)

```python
ONLINE_CONFIG = {
    "BASE_URL": os.getenv("CEREBRAS_BASE_URL"),
    "MODEL_NAME": "openai/qwen-3-235b-a22b-instruct-2507",
}
```

Each agent can be configured with its own model, allowing optimization for specific tasks.

## Extension Points

### Adding a New Agent

1. Create agent folder in `my_agents/`
2. Define `agent.py` with agent configuration
3. Define `prompt.py` with system prompt
4. Register in `agent_runtime.py`
5. Configure handoffs/subagents

### Adding New Tools

1. Create tool function with `@function_tool` decorator
2. Add to appropriate tools module in `tools/`
3. Import and add to agent's tool list

### Custom Personalities

Personalities are defined in `config/agent_personality.py` and can be customized to change the assistant's tone and behavior.
