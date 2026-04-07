"""
graders/style_grader.py — F1-based grader for style issues.

Edge cases
----------
- No style issues in ground truth AND none submitted → score = 1.0 (vacuously correct).
- No style issues in ground truth BUT agent submits style comments
  → those comments are all false positives; score = 0.0.
- Standard F1 otherwise.
"""

from __future__ import annotations

from code_review_env.models import GroundTruthIssue, ReviewComment

from .base_grader import BaseGrader, GradeResult
from .matching import compute_matches

STYLE_CATEGORY: str = "style"


class StyleGrader(BaseGrader):
    """
    Scores agent comments on style issues using F1.

    No bonus is applied; the score is purely the harmonic mean of
    precision and recall over the 'style' category.
    """

    def grade(
        self,
        submitted: list[ReviewComment],
        ground_truth: list[GroundTruthIssue],
    ) -> GradeResult:
        sub_style = [c for c in submitted if c.category.lower() == STYLE_CATEGORY]
        gt_style  = [t for t in ground_truth if t.category.lower() == STYLE_CATEGORY]

        details: list[str] = [
            f"StyleGrader: {len(sub_style)} submitted vs {len(gt_style)} "
            f"ground-truth style issues."
        ]

        # --- Edge case 1: vacuously correct ---
        if not gt_style and not sub_style:
            details.append("No style issues on either side — vacuously correct, score=1.0.")
            return GradeResult(
                score=1.0,
                precision=1.0,
                recall=1.0,
                true_positives=0,
                false_positives=0,
                false_negatives=0,
                details=details,
            )

        # --- Edge case 2: no GT style issues but agent submitted some ---
        if not gt_style and sub_style:
            fp = len(sub_style)
            details.append(
                f"No ground-truth style issues but agent submitted {fp} → "
                f"all are false positives, score=0.0."
            )
            return GradeResult(
                score=0.0,
                precision=0.0,
                recall=1.0,  # recall is vacuously 1.0 (nothing to recall)
                true_positives=0,
                false_positives=fp,
                false_negatives=0,
                details=details,
            )

        matched_truth, matched_sub, unmatched_sub = compute_matches(sub_style, gt_style)

        tp = len(matched_truth)
        fp = len(unmatched_sub)
        fn = len(gt_style) - tp

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


__all__ = ["StyleGrader", "STYLE_CATEGORY"]
