"""
graders/composite_grader.py — Combines bug, security, and style sub-graders.

Reward formula (from spec)
--------------------------
R = max(0.0, min(1.0,
        0.35 × bug_f1
      + 0.30 × sec_score
      + 0.15 × style_f1
      - 0.20 × fp_rate))

FP penalty
----------
fp_rate = total_false_positives / max(total_submitted, 1)
penalty = FP_WEIGHT × fp_rate

NOTE: The critical-miss penalty (−0.30) is NOT applied here; it is applied
in the environment's step() method via penalties.critical_miss_penalty().
This keeps grader logic clean.
"""

from __future__ import annotations

from models import GroundTruthIssue, ReviewComment

from .bug_grader import BugGrader
from .security_grader import SecurityGrader
from .style_grader import StyleGrader

# Weights
WEIGHTS: dict[str, float] = {
    "bug":      0.35,
    "security": 0.30,
    "style":    0.15,
}
FP_WEIGHT: float = 0.20


class CompositeGrader:
    """
    Aggregates scores from BugGrader, SecurityGrader, and StyleGrader into
    a single reward signal in [0.0, 1.0].
    """

    def __init__(self) -> None:
        self._bug_grader  = BugGrader()
        self._sec_grader  = SecurityGrader()
        self._sty_grader  = StyleGrader()

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def grade(
        self,
        submitted_comments: list[ReviewComment],
        ground_truth: list[GroundTruthIssue],
    ) -> float:
        """
        Compute and return the composite reward as a float in [0.0, 1.0].

        Never raises — any exception returns 0.0.
        """
        try:
            return self._compute(submitted_comments, ground_truth)["final"]
        except Exception:
            return 0.0

    def grade_with_details(
        self,
        submitted_comments: list[ReviewComment],
        ground_truth: list[GroundTruthIssue],
    ) -> dict:
        """
        Returns a detailed breakdown dict for logging and inference.py.

        Schema:
        {
            "final":          float,
            "bug_score":      float,
            "security_score": float,
            "style_score":    float,
            "fp_penalty":     float,
            "true_positives": int,
            "false_positives": int,
            "false_negatives": int,
            "bug_details":    list[str],
            "security_details": list[str],
            "style_details":  list[str],
        }
        """
        try:
            return self._compute(submitted_comments, ground_truth)
        except Exception as exc:
            return {
                "final":            0.0,
                "bug_score":        0.0,
                "security_score":   0.0,
                "style_score":      0.0,
                "fp_penalty":       0.0,
                "true_positives":   0,
                "false_positives":  0,
                "false_negatives":  0,
                "bug_details":      [f"Error: {exc}"],
                "security_details": [],
                "style_details":    [],
            }

    # ------------------------------------------------------------------
    # Internal computation
    # ------------------------------------------------------------------

    def _compute(
        self,
        submitted_comments: list[ReviewComment],
        ground_truth: list[GroundTruthIssue],
    ) -> dict:
        bug_result = self._bug_grader.grade(submitted_comments, ground_truth)
        sec_result = self._sec_grader.grade(submitted_comments, ground_truth)
        sty_result = self._sty_grader.grade(submitted_comments, ground_truth)

        # Positive weighted score
        positive = (
            WEIGHTS["bug"]      * bug_result.score
            + WEIGHTS["security"] * sec_result.score
            + WEIGHTS["style"]    * sty_result.score
        )

        # FP penalty across ALL submitted comments (not per-category)
        total_submitted = len(submitted_comments)
        total_fp = (
            bug_result.false_positives
            + sec_result.false_positives
            + sty_result.false_positives
        )
        fp_rate   = total_fp / max(total_submitted, 1)
        fp_penalty = FP_WEIGHT * fp_rate

        # Total TP and FN across all categories
        total_tp = (
            bug_result.true_positives
            + sec_result.true_positives
            + sty_result.true_positives
        )
        total_fn = (
            bug_result.false_negatives
            + sec_result.false_negatives
            + sty_result.false_negatives
        )

        final = max(0.001, min(0.999, positive - fp_penalty))

        return {
            "final":              final,
            "bug_score":          bug_result.score,
            "security_score":     sec_result.score,
            "style_score":        sty_result.score,
            "fp_penalty":         fp_penalty,
            "true_positives":     total_tp,
            "false_positives":    total_fp,
            "false_negatives":    total_fn,
            "bug_details":        bug_result.details,
            "security_details":   sec_result.details,
            "style_details":      sty_result.details,
        }


__all__ = ["CompositeGrader", "WEIGHTS", "FP_WEIGHT"]
