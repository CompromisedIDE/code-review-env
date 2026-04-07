"""
graders/penalties.py — Standalone penalty functions applied by the environment.

These are intentionally decoupled from the sub-graders so that grader logic
remains clean and the environment's step() method has full control over when
and how penalties are applied.
"""

from __future__ import annotations

from code_review_env.models import GroundTruthIssue, ReviewComment
from .matching import compute_matches

CRITICAL_MISS_PENALTY: float = 0.30
"""Penalty deducted when any is_critical ground-truth issue is missed."""


def critical_miss_penalty(
    submitted_comments: list[ReviewComment],
    ground_truth: list[GroundTruthIssue],
) -> float:
    """
    Return CRITICAL_MISS_PENALTY (0.30) if any GroundTruthIssue with
    is_critical=True was not matched by any submitted comment; else 0.0.

    The penalty is binary — it applies once regardless of how many critical
    issues were missed.

    Parameters
    ----------
    submitted_comments : All comments submitted by the agent this step.
    ground_truth       : All ground-truth issues for the current task.

    Returns
    -------
    0.30 if any critical issue was missed, otherwise 0.0.
    """
    critical_issues = [t for t in ground_truth if t.is_critical]

    if not critical_issues:
        return 0.0  # no critical issues → no penalty possible

    # Run matching over all submitted comments vs all ground truth
    matched_truth_indices, _, _ = compute_matches(submitted_comments, ground_truth)

    # Determine which ground-truth indices correspond to critical issues
    critical_gt_indices = {
        idx for idx, t in enumerate(ground_truth) if t.is_critical
    }

    # If any critical index was NOT matched → apply penalty
    unmatched_critical = critical_gt_indices - matched_truth_indices
    if unmatched_critical:
        return CRITICAL_MISS_PENALTY

    return 0.0


__all__ = ["critical_miss_penalty", "CRITICAL_MISS_PENALTY"]
