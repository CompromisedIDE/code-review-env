"""
models.py — Core data models for the Code Review & Security Audit OpenEnv.

All models use Python dataclasses. Field names are canonical and must not
be changed without updating all downstream consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# ReviewComment — agent-submitted comment on a specific code location
# ---------------------------------------------------------------------------

@dataclass
class ReviewComment:
    """A single review comment produced by the agent."""

    file: str = ""
    """Filename (relative path) the comment applies to."""

    line_start: int = 0
    """First line of the highlighted region (1-indexed)."""

    line_end: int = 0
    """Last line of the highlighted region (1-indexed, inclusive)."""

    category: str = ""
    """Issue category: 'bug', 'security', 'style', or 'performance'."""

    severity: str = ""
    """Issue severity: 'low', 'medium', 'high', or 'critical'."""

    cwe_id: Optional[str] = None
    """CWE identifier (e.g. 'CWE-89') for security issues; None otherwise."""

    title: str = ""
    """Short human-readable title for the issue."""

    description: str = ""
    """Full description of the issue."""

    suggested_fix: str = ""
    """Optional suggested code fix or remediation guidance."""


# ---------------------------------------------------------------------------
# ReviewAction — the action the agent submits to the environment
# ---------------------------------------------------------------------------

@dataclass
class ReviewAction:
    """Action submitted by the agent for a single review step."""

    comments: list[ReviewComment] = field(default_factory=list)
    """List of review comments produced by the agent."""

    summary: str = ""
    """Overall summary of the pull-request review."""

    verdict: str = ""
    """Final verdict: 'approve', 'request_changes', or 'comment'."""


# ---------------------------------------------------------------------------
# ReviewObservation — what the environment returns to the agent
# ---------------------------------------------------------------------------

@dataclass
class ReviewObservation:
    """Observation returned to the agent after reset() or step()."""

    # --- Task context ---
    diff: str = ""
    """Unified diff of the pull request."""

    pr_title: str = ""
    """Title of the pull request."""

    pr_description: str = ""
    """Body / description of the pull request."""

    changed_files: list[str] = field(default_factory=list)
    """List of filenames touched by the PR."""

    language: str = ""
    """Primary programming language of the changed files."""

    file_contexts: dict[str, str] = field(default_factory=dict)
    """Mapping of filename → full file content for additional context."""

    # --- Episode metadata ---
    task_id: str = ""
    """Identifier of the current task: 'easy', 'medium', or 'hard'."""

    difficulty: str = ""
    """Human-readable difficulty label matching task_id."""

    max_steps: int = 1
    """Maximum number of steps allowed in this episode."""

    # --- RL signal fields ---
    previous_score: float = 0.0
    """Score from the previous step (0.0 on reset)."""

    previous_feedback: str = ""
    """Textual feedback from the previous step (empty on reset)."""

    done: bool = False
    """True when the episode has ended."""

    reward: float = 0.0
    """Reward received for the last action (0.0 on reset)."""

    # --- Extensible metadata ---
    metadata: dict[str, Any] = field(default_factory=dict)
    """Arbitrary key-value pairs for debugging and logging."""


# ---------------------------------------------------------------------------
# ReviewState — internal episode state snapshot (returned by env.state)
# ---------------------------------------------------------------------------

@dataclass
class ReviewState:
    """Snapshot of the current episode state."""

    task_id: str = ""
    difficulty: str = ""
    current_step: int = 0
    max_steps: int = 1
    submitted: bool = False
    accumulated_reward: float = 0.0
    comments_submitted: int = 0
    episode_id: str = ""


# ---------------------------------------------------------------------------
# GroundTruthIssue — reference annotation used by graders
# ---------------------------------------------------------------------------

@dataclass
class GroundTruthIssue:
    """A single ground-truth issue used to score agent submissions."""

    file: str = ""
    """Filename (relative path) where the issue lives."""

    line_start: int = 0
    """First line of the issue region (1-indexed)."""

    line_end: int = 0
    """Last line of the issue region (1-indexed, inclusive)."""

    category: str = ""
    """Issue category: 'bug', 'security', 'style', or 'performance'."""

    severity: str = ""
    """Issue severity: 'low', 'medium', 'high', or 'critical'."""

    cwe_id: Optional[str] = None
    """CWE identifier for security issues; None otherwise."""

    description: str = ""
    """Human-readable description of the ground-truth issue."""

    issue_id: str = ""
    """Unique identifier for this issue within the task."""

    is_critical: bool = False
    """True if missing this issue incurs the critical-miss penalty."""


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

__all__ = [
    "ReviewComment",
    "ReviewAction",
    "ReviewObservation",
    "ReviewState",
    "GroundTruthIssue",
]
