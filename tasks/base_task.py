"""
tasks/base_task.py — TaskDefinition dataclass.

Holds all data needed to run a single code-review task episode.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from code_review_env.models import GroundTruthIssue


@dataclass
class TaskDefinition:
    """Complete specification for a single code-review task."""

    task_id: str
    """Unique identifier: 'easy', 'medium', or 'hard'."""

    name: str
    """Human-readable task name."""

    difficulty: str
    """Difficulty tier: 'easy' | 'medium' | 'hard'."""

    description: str
    """Short description of what the task tests."""

    diff: str
    """Unified diff the agent must review."""

    file_contexts: dict[str, str]
    """Mapping of filename → full file content for context."""

    ground_truth: list[GroundTruthIssue]
    """Canonical issues used for scoring."""

    max_steps: int = 1
    """Maximum number of review steps allowed (3 for hard only)."""

    pr_title: str = ""
    """Title of the simulated pull request."""

    pr_description: str = ""
    """Body of the simulated pull request."""


__all__ = ["TaskDefinition"]
