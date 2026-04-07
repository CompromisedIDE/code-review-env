"""
inference.py — Inference script for Code Review & Security Audit OpenEnv.

Runs an LLM agent against the environment server via HTTP,
logging results in the required benchmark format.

Usage:
    python inference.py              # Full run with real LLM
    python inference.py --dry-run   # Test log format without API calls
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Optional

import httpx
from openai import OpenAI

# ---------------------------------------------------------------------------
# Environment variables — read exactly these names
# ---------------------------------------------------------------------------

API_BASE_URL  = os.getenv("API_BASE_URL",  "https://router.huggingface.co/v1")
MODEL_NAME    = os.getenv("MODEL_NAME",    "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN      = os.getenv("HF_TOKEN")
API_KEY       = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
LOCAL_ENV_URL = os.getenv("LOCAL_ENV_URL", "http://localhost:7860")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BENCHMARK               = "code-review-env"
MAX_STEPS_PER_TASK      = 3
TEMPERATURE             = 0.3
MAX_TOKENS              = 2000
SUCCESS_SCORE_THRESHOLD = 0.5

DRY_RUN: bool = "--dry-run" in sys.argv

# ---------------------------------------------------------------------------
# Dry-run mock action — used when --dry-run flag is present
# ---------------------------------------------------------------------------

DRY_RUN_ACTION: dict = {
    "comments": [
        {
            "file":         "api/views.py",
            "line_start":   45,
            "line_end":     45,
            "category":     "bug",
            "severity":     "high",
            "cwe_id":       "",
            "title":        "Mock bug",
            "description":  "Dry run mock comment",
            "suggested_fix": "",
        }
    ],
    "summary": "Dry run",
    "verdict": "request_changes",
}

# ---------------------------------------------------------------------------
# Log helpers — all prints use flush=True
# ---------------------------------------------------------------------------

def log_start(task: str, env: str, model: str) -> None:
    """Emit [START] line.  One per task episode."""
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(
    step: int,
    action_str: str,
    reward: float,
    done: bool,
    error: Optional[str],
) -> None:
    """Emit [STEP] line immediately after env.step() returns."""
    done_val  = str(done).lower()          # "true" or "false"
    error_val = error if error is not None else "null"
    print(
        f"[STEP] step={step} action={action_str} "
        f"reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(
    success: bool,
    steps: int,
    score: float,
    rewards: list[float],
) -> None:
    """Emit [END] line.  Always emitted, even on exception."""
    success_val = str(success).lower()     # "true" or "false"
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={success_val} steps={steps} "
        f"score={score:.3f} rewards={rewards_str}",
        flush=True,
    )

# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """
    Return a system prompt that instructs the LLM to act as a senior
    security-focused code reviewer outputting strict JSON only.
    """
    return (
        "You are a senior security-focused code reviewer at a top-tier software company. "
        "Your job is to review Python pull request diffs and identify ALL issues — "
        "bugs, security vulnerabilities (including OWASP Top 10), style violations, "
        "and performance problems — especially subtle ones a junior reviewer might miss.\n\n"
        "For every security issue, include the appropriate CWE identifier "
        "(e.g. CWE-89 for SQL injection, CWE-502 for unsafe deserialization, "
        "CWE-918 for SSRF, CWE-287 for broken authentication, CWE-200 for "
        "sensitive data exposure, CWE-862 for missing authorisation).\n\n"
        "Respond ONLY with a single valid JSON object matching this exact schema. "
        "Do NOT include any preamble, explanation, or markdown code fences:\n\n"
        "{\n"
        '  "comments": [\n'
        "    {\n"
        '      "file": "filename.py",\n'
        '      "line_start": <int>,\n'
        '      "line_end": <int>,\n'
        '      "category": "bug|security|style|performance",\n'
        '      "severity": "critical|high|medium|low",\n'
        '      "cwe_id": "CWE-XX or empty string",\n'
        '      "title": "short title",\n'
        '      "description": "detailed explanation",\n'
        '      "suggested_fix": "optional remediation"\n'
        "    }\n"
        "  ],\n"
        '  "summary": "overall assessment of the pull request",\n'
        '  "verdict": "approve|request_changes|reject"\n'
        "}\n\n"
        "Be thorough. Identify every issue in the diff. "
        "Respond with ONLY the JSON object — nothing else."
    )


def build_user_prompt(
    obs_dict: dict,
    step: int,
    previous_feedback: str,
) -> str:
    """
    Construct the user message from the current observation dict.
    Truncates file contexts to 500 chars each to stay within token limits.
    """
    pr_title       = obs_dict.get("pr_title",       "")
    pr_description = obs_dict.get("pr_description", "")
    diff           = obs_dict.get("diff",           "")
    file_contexts  = obs_dict.get("file_contexts",  {})
    max_steps      = obs_dict.get("max_steps",      1)

    # Truncate file contexts
    ctx_parts: list[str] = []
    for fname, content in file_contexts.items():
        snippet = content[:500] + ("..." if len(content) > 500 else "")
        ctx_parts.append(f"### {fname}\n```python\n{snippet}\n```")
    file_ctx_str = "\n\n".join(ctx_parts)

    parts: list[str] = [
        f"## Pull Request: {pr_title}",
        f"**Description:** {pr_description}",
        "",
        "## Diff",
        "```diff",
        diff,
        "```",
    ]

    if file_ctx_str:
        parts += ["", "## File Contexts (truncated to 500 chars each)", file_ctx_str]

    parts += [
        "",
        "## Review Task",
        f"Step {step} of {max_steps}.",
        "Identify ALL bugs, security vulnerabilities, and style issues in the diff above.",
    ]

    if previous_feedback:
        parts += [
            "",
            "## Feedback from Previous Step",
            previous_feedback,
            "Use this feedback to find the issues you missed in your previous review.",
        ]

    parts += ["", "Respond with ONLY the JSON ReviewAction object."]
    return "\n".join(parts)

# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(client: OpenAI, system_prompt: str, user_prompt: str) -> dict:
    """
    Call the LLM and return a parsed JSON action dict.
    Falls back to an empty action on any error.  Never raises.
    """
    if DRY_RUN:
        return DRY_RUN_ACTION

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        raw = (response.choices[0].message.content or "").strip()

        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```", 2)[-1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        return json.loads(raw)

    except Exception:
        return {"comments": [], "summary": "", "verdict": "request_changes"}

# ---------------------------------------------------------------------------
# Summariser
# ---------------------------------------------------------------------------

def summarize_action(action_dict: dict) -> str:
    """
    Convert an action dict to a short log-safe string.
    Format: "verdict=<verdict> comments=<n>"
    No newlines or special characters.
    """
    verdict    = action_dict.get("verdict", "request_changes")
    n_comments = len(action_dict.get("comments", []))
    return f"verdict={verdict} comments={n_comments}"

# ---------------------------------------------------------------------------
# Task runner — synchronous, called via asyncio.to_thread
# ---------------------------------------------------------------------------

def run_task(
    task_id: str,
    client: OpenAI,
    env_url: str,
    http_client: Optional[httpx.Client] = None,
) -> tuple[float, int]:
    """
    Run one complete episode for *task_id*.

    Returns (final_score, steps_taken).
    Always emits [START] … [STEP]* … [END] regardless of errors.
    """
    own_client = http_client is None
    if own_client:
        http_client = httpx.Client(timeout=60.0)

    rewards:     list[float] = []
    steps_taken: int         = 0
    score:       float       = 0.0
    success:     bool        = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        # ----------------------------------------------------------------
        # Reset environment
        # ----------------------------------------------------------------
        reset_resp = http_client.post(
            f"{env_url}/reset",
            json={"task_id": task_id},
        )
        reset_resp.raise_for_status()
        obs_dict: dict = reset_resp.json()

        system_prompt = build_system_prompt()

        # ----------------------------------------------------------------
        # Episode loop
        # ----------------------------------------------------------------
        for step in range(1, MAX_STEPS_PER_TASK + 1):
            if obs_dict.get("done"):
                break

            previous_feedback = obs_dict.get("previous_feedback", "")
            user_prompt       = build_user_prompt(obs_dict, step, previous_feedback)
            action_dict       = call_llm(client, system_prompt, user_prompt)

            try:
                step_resp = http_client.post(
                    f"{env_url}/step",
                    json=action_dict,
                )
                step_resp.raise_for_status()
                result: dict = step_resp.json()
            except Exception as exc:
                result = {
                    "reward":      0.0,
                    "done":        True,
                    "observation": obs_dict,
                    "info":        {"error": str(exc)},
                }

            reward     = float(result.get("reward", 0.0))
            done       = bool(result.get("done", False))
            error      = result.get("info", {}).get("error", None)
            action_str = summarize_action(action_dict)

            log_step(step, action_str, reward, done, error)

            rewards.append(reward)
            steps_taken = step
            obs_dict    = result.get("observation", obs_dict)

            if done:
                break

        # ----------------------------------------------------------------
        # Score: best step wins — keeps score in [0, 1] naturally
        # ----------------------------------------------------------------
        score   = max(rewards) if rewards else 0.0
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as exc:
        # Something crashed before the loop produced any output
        err_msg = str(exc)
        log_step(steps_taken + 1, "error", 0.0, True, err_msg)
        rewards.append(0.0)
        steps_taken = max(steps_taken, 1)
        score   = 0.0
        success = False

    finally:
        log_end(success, steps_taken, score, rewards)
        if own_client and http_client is not None:
            http_client.close()

    return score, steps_taken

# ---------------------------------------------------------------------------
# Async main
# ---------------------------------------------------------------------------

async def main() -> None:
    """Run all tasks sequentially and print a summary to stderr."""
    try:
        llm_client = OpenAI(
            base_url=API_BASE_URL,
            api_key=API_KEY or "not-set",
        )
    except Exception as exc:
        print(f"[WARN] Could not initialise OpenAI client: {exc}", file=sys.stderr, flush=True)
        llm_client = None  # type: ignore[assignment]
    tasks_to_run = ["easy", "medium", "hard"]
    results: dict[str, tuple[float, int]] = {}

    # Shared sync HTTP client — thread-safe for asyncio.to_thread usage
    sync_http = httpx.Client(timeout=60.0)
    try:
        async with httpx.AsyncClient(timeout=60.0):  # kept for future async use
            for task_id in tasks_to_run:
                score, steps = await asyncio.to_thread(
                    run_task, task_id, llm_client, LOCAL_ENV_URL, sync_http
                )
                results[task_id] = (score, steps)
    finally:
        sync_http.close()

    # Summary to stderr — keeps stdout clean for log parser
    print("\n=== BASELINE SCORES ===", file=sys.stderr, flush=True)
    print(f"easy   : {results.get('easy',   (0.0, 0))[0]:.3f}", file=sys.stderr, flush=True)
    print(f"medium : {results.get('medium', (0.0, 0))[0]:.3f}", file=sys.stderr, flush=True)
    print(f"hard   : {results.get('hard',   (0.0, 0))[0]:.3f}", file=sys.stderr, flush=True)
    avg = sum(s for s, _ in results.values()) / max(len(results), 1)
    print(f"AVERAGE: {avg:.3f}", file=sys.stderr, flush=True)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())
