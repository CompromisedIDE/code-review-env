"""
graders/bug_grader.py — F1-based grader for bug and performance issues.

Per project decision, performance issues are folded into the bug category,
so this grader filters for category == 'bug' OR category == 'performance'.
"""

from __future__ import annotations

from models import GroundTruthIssue, ReviewComment

from .base_grader import BaseGrader, GradeResult
from .matching import compute_matches

# Categories treated as "bugs" for scoring purposes
BUG_CATEGORIES: frozenset[str] = frozenset({"bug", "performance"})


class BugGrader(BaseGrader):
    """
    Scores agent comments on bugs and performance issues using F1.

    Both 'bug' and 'performance' comments/ground-truth issues are included.
    The final score is the harmonic mean of precision and recall (F1).
    """

    def grade(
        self,
        submitted: list[ReviewComment],
        ground_truth: list[GroundTruthIssue],
    ) -> GradeResult:
        # Filter to bug/performance slices
        sub_bug = [c for c in submitted if c.category.lower() in BUG_CATEGORIES]
        gt_bug  = [t for t in ground_truth if t.category.lower() in BUG_CATEGORIES]

        details: list[str] = [
            f"BugGrader: {len(sub_bug)} submitted vs {len(gt_bug)} ground-truth "
            f"bug/performance issues."
        ]

        # Edge case: nothing to grade
        if not sub_bug and not gt_bug:
            details.append("No bug/performance issues on either side — score=1.0.")
            return GradeResult(
                score=1.0,
                precision=1.0,
                recall=1.0,
                true_positives=0,
                false_positives=0,
                false_negatives=0,
                details=details,
            )

        matched_truth, matched_sub, unmatched_sub = compute_matches(sub_bug, gt_bug)

        tp = len(matched_truth)
        fp = len(unmatched_sub)
        fn = len(gt_bug) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        details.append(
            f"TP={tp}, FP={fp}, FN={fn} → precision={precision:.3f}, "
            f"recall={recall:.3f}, F1={f1:.3f}"
        )

        return GradeResult(
            score=f1,
            precision=precision,
            recall=recall,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            details=details,
        )


__all__ = ["BugGrader", "BUG_CATEGORIES"]
