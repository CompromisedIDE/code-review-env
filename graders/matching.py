"""
graders/matching.py — Fuzzy matching between agent comments and ground-truth issues.

Matching rules
--------------
- File must match exactly (path string equality).
- Category must match exactly.
- Line ranges overlap within a ±3 line tolerance.
- Matching is greedy: first unmatched ground-truth issue wins.
- Empty file strings always produce non-matches.
"""

from __future__ import annotations

from code_review_env.models import GroundTruthIssue, ReviewComment

# Line-overlap tolerance (lines)
LINE_TOLERANCE: int = 3


# ---------------------------------------------------------------------------
# Single-pair predicate
# ---------------------------------------------------------------------------

def issues_match(submitted: ReviewComment, truth: GroundTruthIssue) -> bool:
    """
    Return True iff *submitted* is considered a match for *truth*.

    Conditions (all must hold):
    1. Neither file is an empty string.
    2. File paths match exactly.
    3. Categories match exactly (both normalised to lower-case).
    4. Line ranges overlap within LINE_TOLERANCE on both ends.
    """
    # Guard: empty file strings → never match
    if not submitted.file or not truth.file:
        return False

    # File must match exactly
    if submitted.file != truth.file:
        return False

    # Category must match exactly (case-insensitive)
    if submitted.category.lower() != truth.category.lower():
        return False

    # Line-range overlap with ±LINE_TOLERANCE tolerance
    # Expand both ranges by the tolerance and check for overlap.
    sub_start = submitted.line_start - LINE_TOLERANCE
    sub_end   = submitted.line_end   + LINE_TOLERANCE
    tru_start = truth.line_start     - LINE_TOLERANCE
    tru_end   = truth.line_end       + LINE_TOLERANCE

    # Overlap iff one range starts before the other ends
    if sub_end < tru_start or tru_end < sub_start:
        return False

    return True


# ---------------------------------------------------------------------------
# Batch matching
# ---------------------------------------------------------------------------

def compute_matches(
    submitted: list[ReviewComment],
    ground_truth: list[GroundTruthIssue],
) -> tuple[set[int], set[int], set[int]]:
    """
    Greedy matching of submitted comments against ground-truth issues.

    Each ground-truth issue can be claimed by at most one submitted comment,
    and each submitted comment can claim at most one ground-truth issue.
    Matching proceeds in submission order; the first eligible pair wins.

    Returns
    -------
    matched_truth_indices   : indices into *ground_truth* that were matched
    matched_sub_indices     : indices into *submitted* that matched a truth
    unmatched_sub_indices   : indices into *submitted* that had no match
                              (i.e. false positives)
    """
    matched_truth: set[int] = set()
    matched_sub:   set[int] = set()

    for s_idx, comment in enumerate(submitted):
        for t_idx, truth in enumerate(ground_truth):
            if t_idx in matched_truth:
                continue  # already claimed
            if issues_match(comment, truth):
                matched_truth.add(t_idx)
                matched_sub.add(s_idx)
                break  # this comment is used up

    all_sub_indices = set(range(len(submitted)))
    unmatched_sub = all_sub_indices - matched_sub

    return matched_truth, matched_sub, unmatched_sub


__all__ = ["issues_match", "compute_matches", "LINE_TOLERANCE"]
