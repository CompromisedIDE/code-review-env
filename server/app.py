"""
server/app.py — FastAPI application for the Code Review & Security Audit OpenEnv.

Exposes: POST /reset, POST /step, GET /state, GET /health, GET /tasks
Port: 7860 (hackathon requirement)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import ReviewAction, ReviewComment
from server.code_review_environment import CodeReviewEnv
from tasks import REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Code Review OpenEnv starting up on port 7860")
    application.state.env = CodeReviewEnv()
    yield
    logger.info("Code Review OpenEnv shutting down")
    if hasattr(application.state, "env") and application.state.env is not None:
        application.state.env.close()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Code Review & Security Audit OpenEnv Environment",
    version="0.1.0",
    description=(
        "OpenEnv environment where an AI agent reviews Python pull request diffs, "
        "identifying bugs, security vulnerabilities, and style violations."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models — ALL fields Optional with defaults so {} never 422
# ---------------------------------------------------------------------------

class ReviewCommentRequest(BaseModel):
    file: Optional[str] = ""
    line_start: Optional[int] = 0
    line_end: Optional[int] = 0
    category: Optional[str] = "bug"
    severity: Optional[str] = "low"
    cwe_id: Optional[str] = ""
    title: Optional[str] = ""
    description: Optional[str] = ""
    suggested_fix: Optional[str] = ""


class ResetRequest(BaseModel):
    task_id: Optional[str] = "easy"


class StepRequest(BaseModel):
    comments: Optional[list] = []
    summary: Optional[str] = ""
    verdict: Optional[str] = "request_changes"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _obs_to_dict(obs) -> dict:
    """Convert ReviewObservation dataclass to JSON-serialisable dict."""
    return {
        "diff":              obs.diff,
        "pr_title":          obs.pr_title,
        "pr_description":    obs.pr_description,
        "changed_files":     obs.changed_files,
        "language":          obs.language,
        "file_contexts":     obs.file_contexts,
        "task_id":           obs.task_id,
        "difficulty":        obs.difficulty,
        "max_steps":         obs.max_steps,
        "previous_score":    obs.previous_score,
        "previous_feedback": obs.previous_feedback,
        "done":              obs.done,
        "reward":            obs.reward,
        "metadata":          obs.metadata,
    }


def _state_to_dict(state) -> dict:
    """Convert ReviewState dataclass to JSON-serialisable dict."""
    return {
        "task_id":            state.task_id,
        "difficulty":         state.difficulty,
        "current_step":       state.current_step,
        "max_steps":          state.max_steps,
        "submitted":          state.submitted,
        "accumulated_reward": state.accumulated_reward,
        "comments_submitted": state.comments_submitted,
        "episode_id":         state.episode_id,
    }


def _get_env(request) -> CodeReviewEnv:
    """Retrieve the shared env from app.state, creating it if absent."""
    if not hasattr(request.app.state, "env") or request.app.state.env is None:
        request.app.state.env = CodeReviewEnv()
    return request.app.state.env


def _build_action(req: StepRequest) -> ReviewAction:
    """Convert StepRequest → ReviewAction with proper ReviewComment objects."""
    raw_comments = req.comments or []
    comments: list[ReviewComment] = []
    for c in raw_comments:
        if isinstance(c, dict):
            comments.append(
                ReviewComment(
                    file=c.get("file", ""),
                    line_start=c.get("line_start", 0),
                    line_end=c.get("line_end", 0),
                    category=c.get("category", "bug"),
                    severity=c.get("severity", "low"),
                    cwe_id=c.get("cwe_id") or None,
                    title=c.get("title", ""),
                    description=c.get("description", ""),
                    suggested_fix=c.get("suggested_fix", ""),
                )
            )
        elif isinstance(c, ReviewComment):
            comments.append(c)
    return ReviewAction(
        comments=comments,
        summary=req.summary or "",
        verdict=req.verdict or "",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

from fastapi import Request  # noqa: E402 (imported after app for clarity)


@app.post("/reset")
async def reset(body: ResetRequest, request: Request) -> dict:
    """
    Reset the environment to start a new episode.

    Accepts an empty JSON body {} (task_id defaults to 'easy').
    """
    env = _get_env(request)
    task_id = body.task_id or "easy"
    obs = env.reset(task_id)
    return _obs_to_dict(obs)


@app.post("/step")
async def step(body: StepRequest, request: Request) -> dict:
    """
    Submit a review action for the current episode step.
    """
    if not hasattr(request.app.state, "env") or request.app.state.env is None:
        raise HTTPException(status_code=400, detail="Call /reset first")

    env: CodeReviewEnv = request.app.state.env
    if not env._initialized:
        raise HTTPException(status_code=400, detail="Call /reset first")

    action = _build_action(body)
    obs, reward, done, info = env.step(action)

    return {
        "observation": _obs_to_dict(obs),
        "reward":      reward,
        "done":        done,
        "info":        info,
    }


@app.get("/state")
async def state(request: Request) -> dict:
    """Return the current episode state snapshot."""
    if not hasattr(request.app.state, "env") or request.app.state.env is None:
        return {}
    env: CodeReviewEnv = request.app.state.env
    if not env._initialized:
        return {}
    return _state_to_dict(env.state)


@app.get("/health")
async def health() -> dict:
    """Liveness probe — always returns 200."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/tasks")
async def tasks() -> list:
    """List all registered tasks."""
    return REGISTRY.list_tasks()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, log_level="info")
