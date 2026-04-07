"""
tasks/task_registry.py — Central registry for all task definitions.

Registration happens in tasks/__init__.py when each task module is imported.
This module intentionally does NOT auto-register tasks.
"""

from __future__ import annotations

from code_review_env.tasks.base_task import TaskDefinition


class TaskRegistry:
    """Stores and retrieves TaskDefinition objects by task_id."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskDefinition] = {}

    def register(self, task: TaskDefinition) -> None:
        """
        Register a task definition.

        Parameters
        ----------
        task : TaskDefinition
            The task to register.  Overwrites any existing task with the
            same task_id (allows hot-reload during development).
        """
        self._tasks[task.task_id] = task

    def get(self, task_id: str) -> TaskDefinition:
        """
        Return the TaskDefinition for *task_id*.

        Raises
        ------
        KeyError
            If no task with *task_id* has been registered.
        """
        if task_id not in self._tasks:
            raise KeyError(
                f"No task with id '{task_id}' is registered. "
                f"Available: {sorted(self._tasks.keys())}"
            )
        return self._tasks[task_id]

    def list_tasks(self) -> list[dict]:
        """
        Return a summary list of all registered tasks.

        Each entry is a dict with keys:
          id, difficulty, name, description, max_steps
        """
        return [
            {
                "id":          t.task_id,
                "difficulty":  t.difficulty,
                "name":        t.name,
                "description": t.description,
                "max_steps":   t.max_steps,
            }
            for t in self._tasks.values()
        ]


# ---------------------------------------------------------------------------
# Global singleton instance — imported by tasks/__init__.py and the env
# ---------------------------------------------------------------------------

REGISTRY = TaskRegistry()

__all__ = ["TaskRegistry", "REGISTRY"]
