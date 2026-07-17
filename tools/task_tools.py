"""
Task Management Tools for Agent Long-Running Tasks

These tools allow agents to create, manage, and track multi-step tasks
with persistence for resumption across sessions.
"""

from agents import function_tool
import pathlib
from tools.utils.task_manager import TaskManager

# Initialize task manager with storage path
_task_storage_path = pathlib.Path(__file__).parent.parent
_task_storage_path = _task_storage_path.resolve() / "memory_store"
_task_storage_path.mkdir(parents=True, exist_ok=True)
_task_manager = TaskManager(str(_task_storage_path))


# =============================================================================
# Task Creation & Management
# =============================================================================


@function_tool
def create_task(
    title: str,
    description: str = "",
    steps: str = "",
    priority: str = "medium",
    tags: str = "",
) -> str:
    """
    Create a new task with optional steps for tracking long-running work.

    Use this to break down complex requests into manageable steps that can be
    tracked and resumed if interrupted.

    Args:
        title: Clear, concise task title
        description: Detailed description of what needs to be accomplished
        steps: Pipe-separated list of step titles (e.g., "Research topic|Create outline|Write content")
        priority: Task priority - low, medium, high, or critical
        tags: Comma-separated tags for categorization (e.g., "research,writing")

    Returns:
        Task details including ID for future reference

    Example:
        create_task(
            title="Research AI Safety",
            description="Comprehensive research on AI safety practices",
            steps="Gather sources|Analyze key themes|Synthesize findings|Write summary",
            priority="high",
            tags="research,ai"
        )
    """
    try:
        # Parse steps from pipe-separated string
        step_list = None
        if steps.strip():
            step_titles = [s.strip() for s in steps.split("|") if s.strip()]
            step_list = [{"title": t} for t in step_titles]

        # Parse tags from comma-separated string
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        task = _task_manager.create_task(
            title=title,
            description=description,
            steps=step_list,
            priority=priority,
            tags=tag_list,
        )

        return _task_manager.format_task_display(task)
    except Exception as e:
        return f"Error creating task: {e}"


@function_tool
def add_task_step(
    task_id: str,
    step_title: str,
    step_description: str = "",
) -> str:
    """
    Add a new step to an existing task.

    Args:
        task_id: The task ID to add the step to
        step_title: Title of the new step
        step_description: Optional detailed description

    Returns:
        Updated task details
    """
    try:
        step = _task_manager.add_step(task_id, step_title, step_description)
        if not step:
            return f"Error: Task '{task_id}' not found"

        task = _task_manager.get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found"
        return _task_manager.format_task_display(task)
    except Exception as e:
        return f"Error adding step: {e}"


@function_tool
def list_tasks(
    status: str = "",
    include_completed: bool = False,
    tags: str = "",
) -> str:
    """
    List all tasks with optional filtering.

    Args:
        status: Filter by status (not_started, in_progress, completed, failed, blocked)
        include_completed: Whether to include completed tasks
        tags: Comma-separated tags to filter by

    Returns:
        List of tasks with their status and progress
    """
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        status_filter = status if status else None

        tasks = _task_manager.list_tasks(
            status=status_filter,
            tags=tag_list,
            include_completed=include_completed,
        )

        if not tasks:
            return "No tasks found matching the criteria."

        lines = ["# Task List\n"]
        for task in tasks:
            progress = task.get_progress()
            status_icons = {
                "not_started": "⬜",
                "in_progress": "🔄",
                "completed": "✅",
                "failed": "❌",
                "blocked": "🚫",
            }
            icon = status_icons.get(task.status.value, "❓")

            lines.append(f"- **[{task.id}]** {icon} {task.title}")
            lines.append(
                f"  Priority: {task.priority.value} | Progress: {progress['completed']}/{progress['total']} ({progress['percentage']}%)"
            )
            if task.tags:
                lines.append(f"  Tags: {', '.join(task.tags)}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing tasks: {e}"


@function_tool
def get_task_details(task_id: str) -> str:
    """
    Get detailed information about a specific task.

    Args:
        task_id: The task ID to retrieve

    Returns:
        Full task details including all steps and their status
    """
    try:
        task = _task_manager.get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found"

        return _task_manager.format_task_display(task)
    except Exception as e:
        return f"Error getting task: {e}"


@function_tool
def delete_task(task_id: str) -> str:
    """
    Delete a task.

    Args:
        task_id: The task ID to delete

    Returns:
        Confirmation message
    """
    try:
        task = _task_manager.get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found"

        title = task.title
        if _task_manager.delete_task(task_id):
            return f"✅ Successfully deleted task '{title}' ({task_id})"
        return f"Error: Could not delete task '{task_id}'"
    except Exception as e:
        return f"Error deleting task: {e}"


# =============================================================================
# Step Progress Tracking
# =============================================================================


@function_tool
def start_step(task_id: str, step_id: str = "") -> str:
    """
    Mark a step as in-progress. If no step_id is provided, starts the next pending step.

    Call this BEFORE beginning work on a step to track progress.

    Args:
        task_id: The task ID
        step_id: Optional specific step ID (if empty, starts next pending step)

    Returns:
        Updated step status
    """
    try:
        if step_id:
            step = _task_manager.start_step(task_id, step_id)
        else:
            step = _task_manager.start_next_step(task_id)

        if not step:
            task = _task_manager.get_task(task_id)
            if not task:
                return f"Error: Task '{task_id}' not found"
            return "No pending steps to start."

        task = _task_manager.get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found"
        return (
            f"🔄 Started step: **{step.title}**\n\n"
            + _task_manager.format_task_display(task)
        )
    except Exception as e:
        return f"Error starting step: {e}"


@function_tool
def complete_step(task_id: str, step_id: str, result: str = "") -> str:
    """
    Mark a step as completed with an optional result summary.

    Call this IMMEDIATELY after finishing work on a step.

    Args:
        task_id: The task ID
        step_id: The step ID to complete
        result: Brief summary of what was accomplished

    Returns:
        Updated task status with next step info
    """
    try:
        step = _task_manager.complete_step(task_id, step_id, result)
        if not step:
            return f"Error: Step '{step_id}' not found in task '{task_id}'"

        task = _task_manager.get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found"

        output = f"✅ Completed step: **{step.title}**\n"
        if result:
            output += f"Result: {result}\n"
        output += "\n" + _task_manager.format_task_display(task)

        # Suggest next step if available
        next_step = task.get_next_step()
        if next_step:
            output += f"\n\n➡️ **Next step:** {next_step.title}"
        elif task.status.value == "completed":
            output += "\n\n🎉 **Task completed!**"

        return output
    except Exception as e:
        return f"Error completing step: {e}"


@function_tool
def fail_step(task_id: str, step_id: str, error: str = "") -> str:
    """
    Mark a step as failed with an error description.

    Use this when a step cannot be completed due to an error or blocker.

    Args:
        task_id: The task ID
        step_id: The step ID that failed
        error: Description of what went wrong

    Returns:
        Updated task status
    """
    try:
        step = _task_manager.fail_step(task_id, step_id, error)
        if not step:
            return f"Error: Step '{step_id}' not found in task '{task_id}'"

        task = _task_manager.get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found"
        return (
            f"❌ Step failed: **{step.title}**\nError: {error}\n\n"
            + _task_manager.format_task_display(task)
        )
    except Exception as e:
        return f"Error marking step as failed: {e}"


@function_tool
def skip_step(task_id: str, step_id: str, reason: str = "") -> str:
    """
    Skip a step (mark as completed with skip note).

    Use when a step is no longer needed or should be bypassed.

    Args:
        task_id: The task ID
        step_id: The step ID to skip
        reason: Optional reason for skipping

    Returns:
        Updated task status
    """
    try:
        step = _task_manager.skip_step(task_id, step_id, reason)
        if not step:
            return f"Error: Step '{step_id}' not found in task '{task_id}'"

        task = _task_manager.get_task(task_id)
        if not task:
            return f"Error: Task '{task_id}' not found"
        return (
            f"⏭️ Skipped step: **{step.title}**\n"
            + _task_manager.format_task_display(task)
        )
    except Exception as e:
        return f"Error skipping step: {e}"


# =============================================================================
# Task Resumption & Context
# =============================================================================


@function_tool
def get_active_tasks() -> str:
    """
    Get all tasks that are currently in progress.

    Use this at the start of a session to see what work is pending.

    Returns:
        List of active tasks with their current step
    """
    try:
        active = _task_manager.get_active_tasks()
        blocked = _task_manager.get_blocked_tasks()
        not_started = [
            t
            for t in _task_manager.list_tasks(include_completed=False)
            if t.status.value == "not_started"
        ]

        if not active and not blocked and not not_started:
            return "No pending tasks. Ready for new work!"

        lines = ["# Active & Pending Tasks\n"]

        if active:
            lines.append("## 🔄 In Progress:")
            for task in active:
                current = task.get_current_step()
                progress = task.get_progress()
                lines.append(f"- **[{task.id}]** {task.title}")
                lines.append(f"  Current step: {current.title if current else 'None'}")
                lines.append(
                    f"  Progress: {progress['completed']}/{progress['total']} ({progress['percentage']}%)"
                )
                lines.append("")

        if blocked:
            lines.append("## 🚫 Blocked:")
            for task in blocked:
                lines.append(f"- **[{task.id}]** {task.title}")
                # Find the failed step
                for step in task.steps:
                    if step.status.value == "failed":
                        lines.append(f"  Failed at: {step.title}")
                        if step.error:
                            lines.append(f"  Error: {step.error[:100]}")
                        break
                lines.append("")

        if not_started:
            lines.append("## ⬜ Not Started:")
            for task in not_started[:5]:  # Limit to 5
                lines.append(f"- **[{task.id}]** {task.title} ({task.priority.value})")
            if len(not_started) > 5:
                lines.append(f"  ... and {len(not_started) - 5} more")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting active tasks: {e}"


@function_tool
def resume_task(task_id: str = "") -> str:
    """
    Resume work on a task. If no task_id provided, resumes the highest priority pending task.

    Args:
        task_id: Optional specific task ID to resume

    Returns:
        Task details with current step ready to work on
    """
    try:
        if task_id:
            task = _task_manager.get_task(task_id)
        else:
            task = _task_manager.get_resumable_task()

        if not task:
            return "No tasks available to resume."

        current = task.get_current_step()

        output = ["# Resuming Task\n"]
        output.append(_task_manager.format_task_display(task))

        if current:
            output.append("\n\n## Ready to Work On:")
            output.append(f"**Step:** {current.title}")
            if current.description:
                output.append(f"**Details:** {current.description}")

            # Include saved context if available
            if task.context:
                output.append("\n**Saved Context:**")
                for key, value in task.context.items():
                    output.append(f"- {key}: {str(value)[:200]}")

        return "\n".join(output)
    except Exception as e:
        return f"Error resuming task: {e}"


@function_tool
def save_task_context(task_id: str, key: str, value: str) -> str:
    """
    Save context information for a task to help with resumption.

    Use this to store important information that will help resume
    the task later (e.g., file paths, intermediate results, decisions made).

    Args:
        task_id: The task ID
        key: Context key (e.g., "working_file", "last_search_results")
        value: Context value to save

    Returns:
        Confirmation message
    """
    try:
        if _task_manager.save_task_context(task_id, key, value):
            return f"✅ Saved context '{key}' for task {task_id}"
        return f"Error: Task '{task_id}' not found"
    except Exception as e:
        return f"Error saving context: {e}"


@function_tool
def get_task_context(task_id: str) -> str:
    """
    Retrieve all saved context for a task.

    Args:
        task_id: The task ID

    Returns:
        All saved context data
    """
    try:
        context = _task_manager.get_task_context(task_id)
        if context is None:
            return f"Error: Task '{task_id}' not found"

        if not context:
            return f"No context saved for task {task_id}"

        lines = [f"# Context for Task {task_id}\n"]
        for key, value in context.items():
            lines.append(f"**{key}:**")
            lines.append(f"```\n{value}\n```\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting context: {e}"


@function_tool
def update_task_status(
    task_id: str,
    status: str = "",
    priority: str = "",
) -> str:
    """
    Update a task's status or priority.

    Args:
        task_id: The task ID
        status: New status (not_started, in_progress, completed, failed, blocked, cancelled)
        priority: New priority (low, medium, high, critical)

    Returns:
        Updated task details
    """
    try:
        task = _task_manager.update_task(
            task_id,
            status=status if status else None,
            priority=priority if priority else None,
        )

        if not task:
            return f"Error: Task '{task_id}' not found"

        return _task_manager.format_task_display(task)
    except Exception as e:
        return f"Error updating task: {e}"


# =============================================================================
# Convenience exports
# =============================================================================

TASK_TOOLS = [
    create_task,
    add_task_step,
    list_tasks,
    get_task_details,
    delete_task,
    start_step,
    complete_step,
    fail_step,
    skip_step,
    get_active_tasks,
    resume_task,
    save_task_context,
    get_task_context,
    update_task_status,
]
