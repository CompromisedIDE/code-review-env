---
title: Code Review & Security Audit Environment
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
tags:
  - openenv
  - code-review
  - security
  - reinforcement-learning
  - agent-evaluation
short_description: AI agents identify bugs and vulnerabilities.
---

# Code Review & Security Audit — OpenEnv Environment

## Overview

This environment puts an AI agent in the role of a senior security-focused code reviewer, tasked with analysing Python pull request diffs and identifying bugs, security vulnerabilities, and style violations across three progressively harder tasks. Unlike toy benchmarks, every task is grounded in real engineering failures: an off-by-one pagination bug, a JWT expiry bypass, a pickle deserialization RCE — the same classes of issues that routinely cause production incidents and security breaches. For the RL and agent-evaluation community, this environment offers a richly contextual, language-grounded task with genuine real-world utility: catching one CWE-502 before merge is worth more than any synthetic puzzle.

What makes this environment technically interesting is its fully deterministic, LLM-free grading pipeline. Issue matching uses a ±3 line tolerance fuzzy algorithm with exact file and category matching, so agents receive consistent rewards across evaluation runs. The composable grader architecture separates BugGrader, SecurityGrader, and StyleGrader into independent F1-score components combined by a configurable CompositeGrader — making reward shaping transparent and auditable. The hard task introduces a three-step multi-step episode where partial feedback is returned between steps without revealing which specific issues were missed, giving frontier models a chance to refine their reviews and researchers a signal of iterative reasoning quality.

## Quick Start

### Run Locally

```bash
git clone <your-repo-url>
cd code-review-env
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

### Run with Docker

```bash
docker build -t code-review-env .
docker run -p 7860:7860 code-review-env
```

### Run Inference

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="your-token-here"
python inference.py

# Test without API credits
python inference.py --dry-run
```

## API Reference

### Endpoints

| Method | Endpoint  | Description                                      |
|--------|-----------|--------------------------------------------------|
| POST   | `/reset`  | Start a new episode, returns initial observation |
| POST   | `/step`   | Submit a review action, returns reward and obs   |
| GET    | `/state`  | Get the current episode state snapshot           |
| GET    | `/health` | Liveness probe — always returns 200              |
| GET    | `/tasks`  | List all available tasks with metadata           |

### Example: Full Episode via curl

**1. Start a new episode (easy task)**

```bash
curl -s -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "easy"}' | python -m json.tool
```

**2. Submit a review action**

```bash
curl -s -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "comments": [
      {
        "file": "api/views.py",
        "line_start": 45,
        "line_end": 45,
        "category": "bug",
        "severity": "high",
        "cwe_id": "",
        "title": "Off-by-one in pagination offset",
        "description": "Using (page + 1) * page_size skips the first page of results. Correct formula is page * page_size.",
        "suggested_fix": "offset = page * page_size"
      },
      {
        "file": "api/views.py",
        "line_start": 46,
        "line_end": 46,
        "category": "security",
        "severity": "critical",
        "cwe_id": "CWE-89",
        "title": "SQL Injection via f-string interpolation",
        "description": "The query is constructed using f-string interpolation of user-controlled values, allowing an attacker to inject arbitrary SQL.",
        "suggested_fix": "Use parameterised queries: db.execute_raw(query, (page_size, offset))"
      }
    ],
    "summary": "Two issues found: an off-by-one pagination bug and a critical SQL injection vulnerability.",
    "verdict": "request_changes"
  }' | python -m json.tool
```

**3. Check current state**

```bash
curl -s http://localhost:7860/state | python -m json.tool
```

## Observation Space

| Field               | Type            | Description                                                   |
|---------------------|-----------------|---------------------------------------------------------------|
| `diff`              | string          | Unified diff of the pull request                              |
| `pr_title`          | string          | Title of the pull request                                     |
| `pr_description`    | string          | Description of the pull request                               |
| `changed_files`     | array[string]   | List of files changed in the diff                             |
| `language`          | string          | Programming language (default: `python`)                      |
| `file_contexts`     | object          | Full file contents before the diff, keyed by filename         |
| `task_id`           | string          | Current task identifier (`easy`, `medium`, `hard`)            |
| `difficulty`        | string          | `easy`, `medium`, or `hard`                                   |
| `max_steps`         | integer         | Maximum number of steps allowed in this episode               |
| `previous_score`    | float \[0, 1\]  | Score achieved in the previous step (multi-step episodes)     |
| `previous_feedback` | string          | Vague partial feedback for hard task multi-step refinement    |
| `done`              | boolean         | Whether the episode has ended                                 |
| `reward`            | float \[0, 1\]  | Reward received from the last step                            |
| `metadata`          | object          | Additional episode metadata (episode_id, step count, etc.)   |

## Action Space

### ReviewAction

| Field      | Type                   | Description                              |
|------------|------------------------|------------------------------------------|
| `comments` | array\[ReviewComment\] | List of review comments on the diff      |
| `summary`  | string                 | Overall PR assessment in plain text      |
| `verdict`  | string                 | `approve`, `request_changes`, or `reject`|

### ReviewComment

| Field           | Type    | Description                                          |
|-----------------|---------|------------------------------------------------------|
| `file`          | string  | Filename being reviewed                              |
| `line_start`    | integer | Starting line number of the issue in the file        |
| `line_end`      | integer | Ending line number of the issue in the file          |
| `category`      | string  | `bug`, `security`, `style`, or `performance`         |
| `severity`      | string  | `critical`, `high`, `medium`, or `low`               |
| `cwe_id`        | string  | CWE identifier e.g. `CWE-89` (security issues only) |
| `title`         | string  | Short, human-readable issue summary                  |
| `description`   | string  | Detailed explanation of the issue and its impact     |
| `suggested_fix` | string  | Optional suggested code fix or remediation           |

## Reward Function

```
R_final = max(0.0, min(1.0,
    0.35 × R_bug
  + 0.30 × R_security
  + 0.15 × R_style
  - 0.20 × FP_rate
  - 0.30 × critical_miss_penalty
))
```

**Where:**

- **R_bug** — F1 score for bug detection (performance issues fold into this category)
- **R_security** — F1 score for security issues + CWE bonus (0.15 per correct CWE-ID matched, capped at 0.30 total)
- **R_style** — F1 score for style violations; vacuous correctness (0 issues found, 0 ground truth) scores 1.0
- **FP_rate** — `false_positives / total_submitted`; penalises hallucinated comments
- **critical_miss_penalty** — flat 0.30 deduction if any issue marked `is_critical=True` was not matched

Issue matching uses ±3 line tolerance so agents are not penalised for minor line number imprecision. Exact file name and category match are still required.

**Example scores:**

| Scenario                              | Score       |
|---------------------------------------|-------------|
| Perfect answer on easy task           | ~0.80       |
| Found bug only, missed SQL injection  | ~0.50       |
| Perfect answer on hard task           | ~0.75–0.85  |
| Empty submission                      | 0.00        |

## Tasks

### Easy: Off-by-One in Pagination

- **Difficulty:** Easy
- **Max steps:** 1
- **Files changed:** 1 (`api/views.py`)
- **Issues:** 2 (1 bug, 1 security)

A Flask pagination endpoint introduces an off-by-one error in the offset calculation (`(page + 1) * page_size` instead of `page * page_size`) and constructs a raw SQL query via f-string interpolation, creating a SQL injection vulnerability (CWE-89). Both issues appear in the same short function, testing whether the agent catches the obvious arithmetic bug while also recognising the adjacent security flaw.

### Medium: Auth Service Refactor

- **Difficulty:** Medium
- **Max steps:** 1
- **Files changed:** 2 (`auth/token_validator.py`, `users/profile.py`)
- **Issues:** 4 (1 bug, 2 security, 1 style)

A Django/DRF authentication service refactor passes `verify_exp=False` to `jwt.decode` when the parameter is toggled off (CWE-287 — JWT expiry bypass), grants elevated privileges based on an unverified role claim in the payload (privilege escalation), contains redundant and duplicated exception handling, and fetches user-supplied avatar URLs without validating internal/private addresses (CWE-918 — SSRF). Tests multi-file reasoning and the ability to recognise subtle authentication security patterns.

### Hard: Payment Processing PR

- **Difficulty:** Hard
- **Max steps:** 3
- **Files changed:** 5 (`payments/processor.py`, `payments/serializers.py`, `payments/api.py`, `payments/models.py`, `config/logging_config.py`)
- **Issues:** 8 (3 bug, 4 security, 1 style)

A realistic FastAPI payment service PR containing: pickle deserialization of user-supplied bytes enabling RCE (CWE-502), sensitive deserialized data written to logs (CWE-532), in-memory cache replacing the DB duplicate-check creating a race condition across workers, an unbounded dict causing a memory leak, SSN exposure via an unguarded `include_internal` flag (CWE-200), client-trusted `is_admin` flag granting privilege escalation (CWE-862), `Float` column type for monetary amounts causing rounding errors, and a hardcoded `/tmp/payments.log` path. The multi-step episode design lets the agent receive vague partial feedback between steps and refine its review — designed to challenge frontier models.

## Environment Design

### Why Code Review?

Code review is a task every software engineer performs daily, and AI-assisted security auditing has direct, quantifiable economic value — a single missed vulnerability can cost millions in breach remediation, and bug bounty programmes pay tens of thousands for critical CVEs. Despite this, no existing OpenEnv environment targets code review or security auditing as a domain. This environment fills that gap and directly addresses the hackathon's real-world utility scoring criterion: the task matters to engineers, to security teams, and to anyone who ships software.

### Grader Architecture

The grading pipeline is built from three composable, independent grader classes: `BugGrader`, `SecurityGrader`, and `StyleGrader`. Each computes its own F1 score against the ground truth using a fuzzy line-matching algorithm with ±3 line tolerance. `CompositeGrader` combines them with configurable weights and applies the false-positive penalty. The entire grading path is deterministic and contains zero LLM calls — the same submission always receives the same reward, critical for reproducible research and fair competition evaluation.

### Dense Reward Signal

The reward function is deliberately dense rather than sparse: an agent receives partial credit for each correctly identified issue, a CWE accuracy bonus for precise vulnerability classification, a false-positive penalty that discourages hallucination, and a critical-miss deduction for overlooking must-catch vulnerabilities. This means every step returns a meaningful learning signal — an agent that finds one of two issues scores ~0.50, not zero. For the hard multi-step task, intermediate partial feedback gives the agent information to reason about what it missed without leaking the exact answers.

### Future Roadmap: The Path to Production

While the current environment uses a high-quality `TaskRegistry`, the architecture is designed for a direct upgrade path to **Production-Scale Live Evaluation**:

1.  **GitHubPRLoader Integration**: A pending integration that will allow the environment to pull live pull requests from public repositories with high security-focus (e.g., CPython, Django, FastAPI).
2.  **Human-in-the-Loop Ground Truth**: A mechanism to ingest human review comments from real PRs and map them to our structured `GroundTruthIssue` model, creating a 30/30 utility experience where agents are evaluated against the most experienced engineers in the world.
3.  **LSP-Powered Semantic Grader**: Upgrading the fuzzy line matcher to a semantic matcher using Language Server Protocol (LSP) to understand if an agent identified the correct *expression* or *statement*, even if the line numbers differ significantly.

By catching one critical RCE in a production environment, this agentic approach delivers more concrete value than any purely generative task.

## Setup Instructions

### Prerequisites

- Python 3.11+
- Docker (for containerised deployment on HF Spaces)
- An OpenAI-compatible API endpoint (Hugging Face Inference API, local vLLM, etc.)

### Environment Variables

| Variable        | Required | Default                              | Description                              |
|-----------------|----------|--------------------------------------|------------------------------------------|
| `API_BASE_URL`  | No       | `https://router.huggingface.co/v1`   | LLM API base URL                         |
| `MODEL_NAME`    | No       | `Qwen/Qwen2.5-72B-Instruct`          | Model identifier to use for inference    |
| `HF_TOKEN`      | Yes      | —                                    | Hugging Face API key for LLM access      |
| `LOCAL_ENV_URL` | No       | `http://localhost:7860`              | Environment server URL for inference.py  |

### Running Tests

```bash
pytest tests/ -v
```

## License

BSD-3-Clause © 2025 Sesham Raju
