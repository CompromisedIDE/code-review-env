"""
graders/base_grader.py — Abstract base class and shared result type for all graders.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models import GroundTruthIssue, ReviewComment


# ---------------------------------------------------------------------------
# GradeResult — value object returned by every grader
# ---------------------------------------------------------------------------

@dataclass
class GradeResult:
    """Structured result produced by a single grader."""

    score: float = 0.0
    """Normalised score in [0.0, 1.0]."""

    precision: float = 0.0
    """True positives / (true positives + false positives)."""

    recall: float = 0.0
    """True positives / (true positives + false negatives)."""

    true_positives: int = 0
    """Number of submitted comments that matched a ground-truth issue."""

    false_positives: int = 0
    """Number of submitted comments that did NOT match any ground-truth issue."""

    false_negatives: int = 0
    """Number of ground-truth issues that were NOT matched by any comment."""

    details: list[str] = field(default_factory=list)
    """Human-readable diagnostic strings for debugging and feedback."""


# ---------------------------------------------------------------------------
# BaseGrader — abstract interface every grader must implement
# ---------------------------------------------------------------------------

class BaseGrader(ABC):
    """Abstract base for all category-specific graders."""

    @abstractmethod
    def grade(
        self,
        submitted: list["ReviewComment"],
        ground_truth: list["GroundTruthIssue"],
    ) -> GradeResult:
        """
        Score the submitted comments against the ground-truth issues.

        Parameters
        ----------
        submitted:      All comments submitted by the agent for this step.
        ground_truth:   All ground-truth issues for the current task.

        Returns
        -------
        GradeResult with score in [0.0, 1.0] and diagnostic details.
        """


__all__ = ["GradeResult", "BaseGrader"]
