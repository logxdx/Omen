"""
Task Management System for Long-Running Agent Tasks

This module provides a persistent task management system that helps agents
break down complex tasks into steps, track progress, and resume interrupted work.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class TaskStatus(str, Enum):
    """Status of a task or step."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Priority levels for tasks."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TaskStep:
    """Represents a single step within a task."""
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.NOT_STARTED
    result: str = ""
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskStep":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "not_started")),
            result=data.get("result", ""),
            error=data.get("error", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Task:
    """Represents a task with multiple steps."""
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.NOT_STARTED
    priority: TaskPriority = TaskPriority.MEDIUM
    steps: list[TaskStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)  # Store relevant context for resumption
    parent_task_id: Optional[str] = None  # For subtask relationships

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "tags": self.tags,
            "context": self.context,
            "parent_task_id": self.parent_task_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "not_started")),
            priority=TaskPriority(data.get("priority", "medium")),
            steps=[TaskStep.from_dict(s) for s in data.get("steps", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            completed_at=data.get("completed_at"),
            tags=data.get("tags", []),
            context=data.get("context", {}),
            parent_task_id=data.get("parent_task_id"),
        )

    def get_progress(self) -> dict:
        """Calculate task progress."""
        total_steps = len(self.steps)
        if total_steps == 0:
            return {"total": 0, "completed": 0, "percentage": 0}
        
        completed = sum(1 for s in self.steps if s.status == TaskStatus.COMPLETED)
        return {
            "total": total_steps,
            "completed": completed,
            "percentage": round((completed / total_steps) * 100, 1)
        }

    def get_current_step(self) -> Optional[TaskStep]:
        """Get the current in-progress step, or the next not-started step."""
        for step in self.steps:
            if step.status == TaskStatus.IN_PROGRESS:
                return step
        for step in self.steps:
            if step.status == TaskStatus.NOT_STARTED:
                return step
        return None

    def get_next_step(self) -> Optional[TaskStep]:
        """Get the next step that hasn't been started."""
        for step in self.steps:
            if step.status == TaskStatus.NOT_STARTED:
                return step
        return None


class TaskManager:
    """
    Manages tasks with persistence to disk.
    
    Tasks are stored as JSON files in a designated directory,
    allowing for resumption across sessions.
    """

    def __init__(self, storage_path: str | Path):
        self.storage_path = Path(storage_path)
        self.tasks_dir = self.storage_path / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Task] = {}
        self._load_all_tasks()

    def _load_all_tasks(self) -> None:
        """Load all tasks from disk into cache."""
        for task_file in self.tasks_dir.glob("*.json"):
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    task = Task.from_dict(data)
                    self._cache[task.id] = task
            except Exception as e:
                print(f"Warning: Could not load task file {task_file}: {e}")

    def _save_task(self, task: Task) -> None:
        """Save a task to disk."""
        task.updated_at = datetime.now().isoformat()
        task_file = self.tasks_dir / f"{task.id}.json"
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task.to_dict(), f, indent=2)
        self._cache[task.id] = task

    def _delete_task_file(self, task_id: str) -> None:
        """Delete a task file from disk."""
        task_file = self.tasks_dir / f"{task_id}.json"
        if task_file.exists():
            task_file.unlink()
        if task_id in self._cache:
            del self._cache[task_id]

    # =========================================================================
    # Task CRUD Operations
    # =========================================================================

    def create_task(
        self,
        title: str,
        description: str = "",
        steps: list[dict] | None = None,
        priority: str = "medium",
        tags: list[str] | None = None,
        context: dict | None = None,
        parent_task_id: str | None = None,
    ) -> Task:
        """
        Create a new task with optional steps.
        
        Args:
            title: Task title
            description: Detailed description
            steps: List of step dicts with 'title' and optional 'description'
            priority: Task priority (low, medium, high, critical)
            tags: List of tags for categorization
            context: Additional context data for resumption
            parent_task_id: Parent task ID for subtasks
            
        Returns:
            The created Task object
        """
        task_id = str(uuid.uuid4())[:8]
        
        task_steps = []
        if steps:
            for i, step_data in enumerate(steps):
                step = TaskStep(
                    id=f"{task_id}-{i+1}",
                    title=step_data.get("title", f"Step {i+1}"),
                    description=step_data.get("description", ""),
                )
                task_steps.append(step)

        task = Task(
            id=task_id,
            title=title,
            description=description,
            steps=task_steps,
            priority=TaskPriority(priority),
            tags=tags or [],
            context=context or {},
            parent_task_id=parent_task_id,
        )
        
        self._save_task(task)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self._cache.get(task_id)

    def list_tasks(
        self,
        status: str | None = None,
        tags: list[str] | None = None,
        include_completed: bool = True,
    ) -> list[Task]:
        """
        List tasks with optional filtering.
        
        Args:
            status: Filter by status
            tags: Filter by tags (any match)
            include_completed: Whether to include completed tasks
            
        Returns:
            List of matching tasks
        """
        tasks = list(self._cache.values())
        
        if status:
            tasks = [t for t in tasks if t.status.value == status]
        
        if not include_completed:
            tasks = [t for t in tasks if t.status != TaskStatus.COMPLETED]
        
        if tags:
            tasks = [t for t in tasks if any(tag in t.tags for tag in tags)]
        
        # Sort by priority and creation date
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        tasks.sort(key=lambda t: (priority_order.get(t.priority.value, 2), t.created_at))
        
        return tasks

    def update_task(
        self,
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None,
        context: dict | None = None,
    ) -> Optional[Task]:
        """Update task properties."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if status is not None:
            task.status = TaskStatus(status)
            if status == "completed":
                task.completed_at = datetime.now().isoformat()
        if priority is not None:
            task.priority = TaskPriority(priority)
        if tags is not None:
            task.tags = tags
        if context is not None:
            task.context.update(context)
        
        self._save_task(task)
        return task

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        if task_id not in self._cache:
            return False
        self._delete_task_file(task_id)
        return True

    # =========================================================================
    # Step Operations
    # =========================================================================

    def add_step(
        self,
        task_id: str,
        title: str,
        description: str = "",
        position: int | None = None,
    ) -> Optional[TaskStep]:
        """Add a step to a task."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        step_num = len(task.steps) + 1
        step = TaskStep(
            id=f"{task_id}-{step_num}",
            title=title,
            description=description,
        )
        
        if position is not None and 0 <= position <= len(task.steps):
            task.steps.insert(position, step)
        else:
            task.steps.append(step)
        
        self._save_task(task)
        return step

    def start_step(self, task_id: str, step_id: str) -> Optional[TaskStep]:
        """Mark a step as in progress."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        for step in task.steps:
            if step.id == step_id:
                step.status = TaskStatus.IN_PROGRESS
                step.started_at = datetime.now().isoformat()
                
                # Also update task status
                if task.status == TaskStatus.NOT_STARTED:
                    task.status = TaskStatus.IN_PROGRESS
                
                self._save_task(task)
                return step
        return None

    def complete_step(
        self,
        task_id: str,
        step_id: str,
        result: str = "",
    ) -> Optional[TaskStep]:
        """Mark a step as completed."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        for step in task.steps:
            if step.id == step_id:
                step.status = TaskStatus.COMPLETED
                step.result = result
                step.completed_at = datetime.now().isoformat()
                
                # Check if all steps are completed
                if all(s.status == TaskStatus.COMPLETED for s in task.steps):
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.now().isoformat()
                
                self._save_task(task)
                return step
        return None

    def fail_step(
        self,
        task_id: str,
        step_id: str,
        error: str = "",
    ) -> Optional[TaskStep]:
        """Mark a step as failed."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        for step in task.steps:
            if step.id == step_id:
                step.status = TaskStatus.FAILED
                step.error = error
                step.completed_at = datetime.now().isoformat()
                
                # Update task status to blocked
                task.status = TaskStatus.BLOCKED
                
                self._save_task(task)
                return step
        return None

    def skip_step(self, task_id: str, step_id: str, reason: str = "") -> Optional[TaskStep]:
        """Skip a step (mark as completed with skip note)."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        for step in task.steps:
            if step.id == step_id:
                step.status = TaskStatus.COMPLETED
                step.result = f"[SKIPPED] {reason}" if reason else "[SKIPPED]"
                step.completed_at = datetime.now().isoformat()
                
                self._save_task(task)
                return step
        return None

    # =========================================================================
    # Workflow Operations
    # =========================================================================

    def start_next_step(self, task_id: str) -> Optional[TaskStep]:
        """Automatically start the next pending step."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        next_step = task.get_next_step()
        if next_step:
            return self.start_step(task_id, next_step.id)
        return None

    def get_active_tasks(self) -> list[Task]:
        """Get all tasks that are currently in progress."""
        return [t for t in self._cache.values() 
                if t.status == TaskStatus.IN_PROGRESS]

    def get_blocked_tasks(self) -> list[Task]:
        """Get all tasks that are blocked."""
        return [t for t in self._cache.values() 
                if t.status == TaskStatus.BLOCKED]

    def get_task_summary(self, task_id: str) -> Optional[dict]:
        """Get a summary of task progress."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        progress = task.get_progress()
        current_step = task.get_current_step()
        
        return {
            "id": task.id,
            "title": task.title,
            "status": task.status.value,
            "priority": task.priority.value,
            "progress": progress,
            "current_step": current_step.title if current_step else None,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    def get_all_summaries(self, include_completed: bool = False) -> list[dict]:
        """Get summaries for all tasks."""
        summaries = []
        for task in self._cache.values():
            if not include_completed and task.status == TaskStatus.COMPLETED:
                continue
            summary = self.get_task_summary(task.id)
            if summary:
                summaries.append(summary)
        return summaries

    # =========================================================================
    # Context & Resumption
    # =========================================================================

    def save_task_context(self, task_id: str, context_key: str, context_value: Any) -> bool:
        """Save context data for task resumption."""
        task = self.get_task(task_id)
        if not task:
            return False
        
        task.context[context_key] = context_value
        self._save_task(task)
        return True

    def get_task_context(self, task_id: str, context_key: Optional[str] = None) -> Any:
        """Get context data for task resumption."""
        task = self.get_task(task_id)
        if not task:
            return None
        
        if context_key:
            return task.context.get(context_key)
        return task.context

    def get_resumable_task(self) -> Optional[Task]:
        """
        Get the highest priority task that can be resumed.
        Returns the most important in-progress or blocked task.
        """
        active = self.get_active_tasks()
        if active:
            # Sort by priority
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            active.sort(key=lambda t: priority_order.get(t.priority.value, 2))
            return active[0]
        
        # Check for tasks that haven't started yet
        not_started = [t for t in self._cache.values() 
                       if t.status == TaskStatus.NOT_STARTED]
        if not_started:
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            not_started.sort(key=lambda t: priority_order.get(t.priority.value, 2))
            return not_started[0]
        
        return None

    def format_task_display(self, task: Task) -> str:
        """Format a task for display."""
        progress = task.get_progress()
        status_icons = {
            "not_started": "⬜",
            "in_progress": "🔄",
            "completed": "✅",
            "failed": "❌",
            "blocked": "🚫",
            "cancelled": "⏹️",
        }
        
        lines = [
            f"## Task: {task.title}",
            f"**ID:** {task.id} | **Status:** {status_icons.get(task.status.value, '❓')} {task.status.value}",
            f"**Priority:** {task.priority.value.upper()} | **Progress:** {progress['completed']}/{progress['total']} ({progress['percentage']}%)",
        ]
        
        if task.description:
            lines.append(f"\n**Description:** {task.description}")
        
        if task.steps:
            lines.append("\n### Steps:")
            for i, step in enumerate(task.steps, 1):
                icon = status_icons.get(step.status.value, "❓")
                step_line = f"  {i}. {icon} {step.title}"
                if step.status == TaskStatus.COMPLETED and step.result:
                    step_line += f"\n     → {step.result[:100]}{'...' if len(step.result) > 100 else ''}"
                elif step.status == TaskStatus.FAILED and step.error:
                    step_line += f"\n     ⚠️ {step.error[:100]}{'...' if len(step.error) > 100 else ''}"
                lines.append(step_line)
        
        return "\n".join(lines)
