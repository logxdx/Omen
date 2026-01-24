# Task Management System

A persistent task management system that helps agents track and complete long-running, multi-step tasks with support for interruption and resumption.

## Features

- **Multi-step task tracking**: Break complex work into manageable steps
- **Persistence**: Tasks are saved to disk and survive session restarts
- **Progress tracking**: Visual progress indicators and completion percentages
- **Context storage**: Save intermediate results for resumption
- **Priority management**: Critical, high, medium, low priorities
- **Tagging**: Categorize tasks for easy filtering

## Quick Start

### Creating a Task

```python
# Via tool call
create_task(
    title="Research AI Safety",
    description="Comprehensive research on AI safety practices",
    steps="Gather sources|Analyze key themes|Synthesize findings|Write summary",
    priority="high",
    tags="research,ai"
)
```

### Working Through Steps

```python
# Start the next pending step
start_step(task_id="abc123")

# Mark step as completed with result
complete_step(task_id="abc123", step_id="abc123-1", result="Found 5 relevant papers")

# If a step fails
fail_step(task_id="abc123", step_id="abc123-2", error="API rate limited")

# Skip a step if not needed
skip_step(task_id="abc123", step_id="abc123-3", reason="Already covered in step 1")
```

### Resuming Work

```python
# Check active tasks at session start
get_active_tasks()

# Resume the highest priority pending task
resume_task()

# Resume a specific task
resume_task(task_id="abc123")
```

### Saving Context

```python
# Save important data for later
save_task_context(task_id="abc123", key="papers_found", value="paper1.pdf, paper2.pdf")

# Retrieve saved context
get_task_context(task_id="abc123")
```

## Tool Reference

| Tool | Purpose |
|------|---------|
| `create_task` | Create a new task with optional steps |
| `add_task_step` | Add a step to an existing task |
| `list_tasks` | List tasks with filtering |
| `get_task_details` | Get full task information |
| `delete_task` | Delete a task |
| `start_step` | Mark a step as in-progress |
| `complete_step` | Mark a step as completed |
| `fail_step` | Mark a step as failed |
| `skip_step` | Skip a step |
| `get_active_tasks` | Get all in-progress tasks |
| `resume_task` | Resume work on a task |
| `save_task_context` | Store context for resumption |
| `get_task_context` | Retrieve stored context |
| `update_task_status` | Change task status/priority |

## Task Statuses

- ⬜ `not_started` - Task hasn't been started
- 🔄 `in_progress` - Task is being worked on
- ✅ `completed` - Task finished successfully
- ❌ `failed` - Task failed (usually due to step failure)
- 🚫 `blocked` - Task blocked by failed step
- ⏹️ `cancelled` - Task was cancelled

## Priority Levels

- `critical` - Urgent, needs immediate attention
- `high` - Important, should be prioritized
- `medium` - Normal priority (default)
- `low` - Can be done when time permits

## Storage

Tasks are persisted in `task_store/tasks/` as JSON files. Each task gets its own file named `{task_id}.json`.

## Best Practices

1. **Start sessions by checking active tasks**: Use `get_active_tasks()` at the beginning of each session
2. **Track progress in real-time**: Call `complete_step()` immediately after finishing each step
3. **Save context frequently**: Use `save_task_context()` to store important intermediate results
4. **Use descriptive step titles**: Make steps clear and actionable (e.g., "Research competitor pricing" not "Step 1")
5. **Handle failures gracefully**: Use `fail_step()` with clear error messages to track blockers
