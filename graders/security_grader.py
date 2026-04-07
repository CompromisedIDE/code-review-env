"""
graders/security_grader.py — F1 + CWE-bonus grader for security issues.

Scoring formula
---------------
base_score  = F1(precision, recall) over security comments
cwe_bonus   = CWE_BONUS_PER_MATCH × (# correctly matched CWE IDs)
              capped at CWE_BONUS_CAP
final_score = min(1.0, base_score + cwe_bonus)
"""

from __future__ import annotations

from code_review_env.models import GroundTruthIssue, ReviewComment

from .base_grader import BaseGrader, GradeResult
from .matching import compute_matches

SECURITY_CATEGORY: str = "security"
CWE_BONUS_PER_MATCH: float = 0.15
CWE_BONUS_CAP: float = 0.30


class SecurityGrader(BaseGrader):
    """
    Scores agent comments on security issues using F1 plus a CWE-ID bonus.

    A CWE bonus is awarded for each matched pair where the agent's submitted
    CWE-ID matches the ground-truth CWE-ID (case-insensitive, stripped).
    """

    def grade(
        self,
        submitted: list[ReviewComment],
        ground_truth: list[GroundTruthIssue],
    ) -> GradeResult:
        sub_sec = [c for c in submitted if c.category.lower() == SECURITY_CATEGORY]
        gt_sec  = [t for t in ground_truth if t.category.lower() == SECURITY_CATEGORY]

        details: list[str] = [
            f"SecurityGrader: {len(sub_sec)} submitted vs {len(gt_sec)} "
            f"ground-truth security issues."
        ]

        # Edge case: nothing to grade
        if not sub_sec and not gt_sec:
            details.append("No security issues on either side — score=1.0.")
            return GradeResult(
                score=1.0,
                precision=1.0,
                recall=1.0,
                true_positives=0,
                false_positives=0,
                false_negatives=0,
                details=details,
            )

        matched_truth, matched_sub, unmatched_sub = compute_matches(sub_sec, gt_sec)

        tp = len(matched_truth)
        fp = len(unmatched_sub)
        fn = len(gt_sec) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        # CWE bonus: iterate over matched pairs and compare CWE IDs
        cwe_matches = 0
        # Rebuild index map: matched_truth contains gt indices, matched_sub
        # contains sub indices — we need the pairing.  Re-run greedy to get pairs.
        cwe_pairs = _collect_matched_pairs(sub_sec, gt_sec)
        for s_idx, t_idx in cwe_pairs:
            sub_cwe = (sub_sec[s_idx].cwe_id or "").strip().upper()
            gt_cwe  = (gt_sec[t_idx].cwe_id  or "").strip().upper()
            if sub_cwe and gt_cwe and sub_cwe == gt_cwe:
                cwe_matches += 1

        cwe_bonus = min(CWE_BONUS_CAP, CWE_BONUS_PER_MATCH * cwe_matches)
        final     = min(1.0, f1 + cwe_bonus)

        details.append(
            f"TP={tp}, FP={fp}, FN={fn} → precision={precision:.3f}, "
            f"recall={recall:.3f}, F1={f1:.3f}"
        )
        details.append(
            f"CWE matches={cwe_matches}, bonus={cwe_bonus:.3f}, "
            f"final_score={final:.3f}"
        )

        return GradeResult(
            score=final,
            precision=precision,
            recall=recall,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            details=details,
        )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _collect_matched_pairs(
    sub_sec: list[ReviewComment],
    gt_sec: list[GroundTruthIssue],
) -> list[tuple[int, int]]:
    """
    Re-run greedy matching and return (sub_idx, gt_idx) pairs for each match.
    Mirrors the logic in compute_matches but captures the actual pairs.
    """
    from .matching import issues_match

    matched_truth: set[int] = set()
    pairs: list[tuple[int, int]] = []

    for s_idx, comment in enumerate(sub_sec):
        for t_idx, truth in enumerate(gt_sec):
            if t_idx in matched_truth:
                continue
            if issues_match(comment, truth):
                matched_truth.add(t_idx)
                pairs.append((s_idx, t_idx))
                break

    return pairs


__all__ = [
    "SecurityGrader",
    "SECURITY_CATEGORY",
    "CWE_BONUS_PER_MATCH",
    "CWE_BONUS_CAP",
]
