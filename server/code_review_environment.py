"""
server/code_review_environment.py — Core RL environment for Code Review & Security Audit.

Implements the Legacy API pattern. Wired to the real TaskRegistry and CompositeGrader.
"""

from __future__ import annotations

import traceback
import uuid
from dataclasses import asdict
from typing import Any, Optional

from models import (
    ReviewAction,
    ReviewComment,
    ReviewObservation,
    ReviewState,
)
from graders import CompositeGrader, critical_miss_penalty
from tasks import REGISTRY
from tasks.base_task import TaskDefinition

# ---------------------------------------------------------------------------
# Try to import the real openenv Environment base; fall back gracefully
# ---------------------------------------------------------------------------

try:
    from openenv import Environment as _BaseEnvironment  # type: ignore
except ImportError:
    class _BaseEnvironment:  # type: ignore
        """Minimal shim so the module is importable without openenv installed."""
        pass


# ---------------------------------------------------------------------------
# CodeReviewEnv
# ---------------------------------------------------------------------------

class CodeReviewEnv(_BaseEnvironment):
    """
    Code Review & Security Audit environment.

    Lifecycle
    ---------
    1. Call reset(task_id) to start a new episode.
    2. Call step(action) one or more times (up to max_steps).
    3. Check obs.done to know when the episode has ended.
    4. Call close() when done to release state.

    Supported task_ids: 'easy', 'medium', 'hard'
    """

    DEFAULT_TASK_ID: str = "easy"

    def __init__(self) -> None:
        self.grader = CompositeGrader()
        self._reset_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, task_id: Optional[str] = None) -> ReviewObservation:
        """
        Start a new episode.

        Parameters
        ----------
        task_id : str | None
            'easy', 'medium', or 'hard'.  Defaults to 'easy'.

        Returns
        -------
        ReviewObservation with done=False, reward=0.0.
        """
        effective_task_id = task_id or self.DEFAULT_TASK_ID

        # Load real task from registry
        task: TaskDefinition = REGISTRY.get(effective_task_id)

        # Clean state — NO leakage from previous episode
        self._reset_state()

        # Populate episode state
        self._task_id        = task.task_id
        self._difficulty     = task.difficulty
        self._max_steps      = task.max_steps
        self.current_task    = task
        self._episode_id     = str(uuid.uuid4())
        self._initialized    = True

        return ReviewObservation(
            diff=task.diff,
            pr_title=task.pr_title,
            pr_description=task.pr_description,
            changed_files=list(task.file_contexts.keys()),
            language="python",
            file_contexts=dict(task.file_contexts),
            task_id=task.task_id,
            difficulty=task.difficulty,
            max_steps=task.max_steps,
            previous_score=0.0,
            previous_feedback="",
            done=False,
            reward=0.0,
            metadata={
                "episode_id":     self._episode_id,
                "developer_mood": "The developer seems cautious but rushed.",
            },
        )

    def step(
        self, action: ReviewAction
    ) -> tuple[ReviewObservation, float, bool, dict]:
        """
        Apply an action and advance the episode.

        Returns (obs, reward, done, info).  Never raises.
        """
        try:
            return self._step_inner(action)
        except Exception as exc:
            error_obs = self._safe_fallback_obs(
                error_msg=f"step() error: {exc}",
                tb=traceback.format_exc(),
            )
            return error_obs, 0.0, error_obs.done, {"error": str(exc)}

    @property
    def state(self) -> ReviewState:
        """Return the current episode state snapshot.  Never raises."""
        return ReviewState(
            task_id=self._task_id,
            difficulty=self._difficulty,
            current_step=self._current_step,
            max_steps=self._max_steps,
            submitted=self._submitted,
            accumulated_reward=self._last_reward,
            comments_submitted=self._comments_submitted,
            episode_id=self._episode_id,
        )

    def close(self) -> None:
        """Clean up episode state. Called by inference.py in finally block."""
        self.current_task = None
        self._episode_id = ""
        self._current_step = 0

    async def aclose(self) -> None:
        """Async version for async inference runners."""
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_state(self) -> None:
        """Zero out all episode state variables."""
        self._task_id:            str                       = ""
        self._difficulty:         str                       = ""
        self._max_steps:          int                       = 1
        self._current_step:       int                       = 0
        self.current_task:        Optional[TaskDefinition]  = None
        self._episode_id:         str                       = ""
        self._submitted:          bool                      = False
        self._last_reward:        float                     = 0.0
        self._last_feedback:      str                       = ""
        self._comments_submitted: int                       = 0
        self._initialized:        bool                      = False

    def _step_inner(
        self, action: ReviewAction
    ) -> tuple[ReviewObservation, float, bool, dict]:
        """Core step logic — may raise; wrapped by step()."""

        if not self._initialized or self.current_task is None:
            raise RuntimeError("reset() must be called before step().")

        if not isinstance(action, ReviewAction):
            raise TypeError(
                f"action must be ReviewAction, got {type(action).__name__}"
            )

        # Collect submitted comments
        comments: list[ReviewComment] = (
            action.comments if action.comments is not None else []
        )

        ground_truth = self.current_task.ground_truth

        # Grade
        base_reward  = self.grader.grade(comments, ground_truth)
        penalty      = critical_miss_penalty(comments, ground_truth)
        raw_reward   = base_reward - penalty

        # Hard clamp to [0.0, 1.0]
        reward = max(0.001, min(0.999, raw_reward))

        # Grade details (used for info dict and multi-step feedback)
        details = self.grader.grade_with_details(comments, ground_truth)

        # Update episode state
        self._current_step       += 1
        self._comments_submitted  = len(comments)
        self._last_reward         = reward

        # Determine done
        # Determine done: only 'approve' or 'reject' are final; 
        # 'request_changes' allows refinement in multi-step episodes.
        is_final_verdict = action.verdict in ["approve", "reject"]
        done = self._current_step >= self._max_steps or is_final_verdict
        self._submitted = done

        # Multi-step feedback for hard task (vague — no specific issue leaks)
        feedback = ""
        if self._difficulty == "hard" and not done:
            found  = details["true_positives"]
            total  = len(ground_truth)
            crit_missed = penalty > 0.0  # critical_miss_penalty > 0 iff critical missed
            feedback = (
                f"Step {self._current_step}: Found {found}/{total} issues. "
                + (
                    "One or more critical issues still missing. "
                    if crit_missed
                    else "No critical issues missed. "
                )
                + "Refine your review."
            )

        self._last_feedback = feedback

        # Build observation
        obs = ReviewObservation(
            diff=self.current_task.diff,
            pr_title=self.current_task.pr_title,
            pr_description=self.current_task.pr_description,
            changed_files=list(self.current_task.file_contexts.keys()),
            language="python",
            file_contexts=dict(self.current_task.file_contexts),
            task_id=self._task_id,
            difficulty=self._difficulty,
            max_steps=self._max_steps,
            previous_score=reward,
            previous_feedback=feedback,
            done=done,
            reward=reward,
            metadata={
                "episode_id":     self._episode_id,
                "current_step":   self._current_step,
                "crit_penalty":   penalty,
                "base_reward":    base_reward,
                "developer_mood": "The developer is awaiting your full review.",
            },
        )

        info: dict = {**details, "episode_id": self._episode_id}

        return obs, reward, done, info

    def _safe_fallback_obs(
        self, error_msg: str, tb: str = ""
    ) -> ReviewObservation:
        """Return a safe observation on unrecoverable error."""
        done = self._current_step >= self._max_steps
        task = self.current_task
        return ReviewObservation(
            diff=task.diff if task else "",
            pr_title=task.pr_title if task else "",
            pr_description=task.pr_description if task else "",
            changed_files=list(task.file_contexts.keys()) if task else [],
            language="python",
            file_contexts=dict(task.file_contexts) if task else {},
            task_id=self._task_id,
            difficulty=self._difficulty,
            max_steps=self._max_steps,
            previous_score=self._last_reward,
            previous_feedback=self._last_feedback,
            done=done,
            reward=0.0,
            metadata={
                "episode_id": self._episode_id,
                "error":      error_msg,
                "traceback":  tb,
            },
        )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    env = CodeReviewEnv()

    obs = env.reset("easy")
    assert obs.done is False
    assert obs.reward == 0.0
    assert obs.task_id == "easy"
    assert len(obs.diff) > 100
    print(f"reset() OK  — episode_id={obs.metadata['episode_id']}")

    from models import ReviewAction
    obs2, reward, done, info = env.step(ReviewAction())
    assert 0.0 <= reward <= 1.0
    assert done is True   # easy has max_steps=1
    assert "bug_score" in info
    print(f"step()  OK  — reward={reward:.4f}, done={done}")

    s = env.state
    assert isinstance(s, ReviewState)
    print(f"state   OK  — {s}")

    env.close()
    print("close() OK")

    obs3 = env.reset("easy")
    assert obs3.done is False
    print("reset() after close() OK")

    print("\n✓ All smoke tests passed")
