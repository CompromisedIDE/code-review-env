"""
tasks/easy/off_by_one.py — Easy task: off-by-one pagination + SQL injection.
"""

from __future__ import annotations

from models import GroundTruthIssue
from tasks.base_task import TaskDefinition

# ---------------------------------------------------------------------------
# Unified diff (byte-for-byte canonical form)
# ---------------------------------------------------------------------------

DIFF = """\
--- a/api/views.py
+++ b/api/views.py
@@ -42,8 +42,8 @@
 def get_paginated_users(page: int, page_size: int = 20) -> list[dict]:
     \"\"\"Return a page of users from the database.\"\"\"
-    offset = page * page_size
+    offset = (page + 1) * page_size
     query = f"SELECT * FROM users ORDER BY id LIMIT {page_size} OFFSET {offset}"
-    results = db.execute(query)
+    results = db.execute_raw(query)
     return [serialize_user(r) for r in results]
"""

# ---------------------------------------------------------------------------
# File context — api/views.py
# Line 45 = offset assignment (inside function body)
# Line 46 = query f-string with LIMIT/OFFSET
# Function starts at line 43 so the ground-truth lines are exact.
# ---------------------------------------------------------------------------

VIEWS_PY = (
    '"""api/views.py — Flask REST API views for the user service."""\n'
    "\n"
    "from flask import Flask, jsonify, request, abort\n"
    "from functools import wraps\n"
    "import logging\n"
    "from db import db\n"
    "from models import User\n"
    "\n"
    "app = Flask(__name__)\n"
    "logger = logging.getLogger(__name__)\n"
    "\n"
    "\n"
    "def require_auth(f):\n"
    "    @wraps(f)\n"
    "    def decorated(*args, **kwargs):\n"
    '        token = request.headers.get("Authorization", "")\n'
    '        if not token.startswith("Bearer "):\n'
    "            abort(401)\n"
    "        return f(*args, **kwargs)\n"
    "    return decorated\n"
    "\n"
    "\n"
    "def serialize_user(row) -> dict:\n"
    "    return {\n"
    '        "id":       row.id,\n'
    '        "username": row.username,\n'
    '        "email":    row.email,\n'
    '        "created":  row.created_at.isoformat(),\n'
    "    }\n"
    "\n"
    "\n"
    '@app.route("/users", methods=["GET"])\n'
    "@require_auth\n"
    "def list_users():\n"
    '    """Return all users (admin only)."""\n'
    '    users = db.execute("SELECT * FROM users")\n'
    "    return jsonify([serialize_user(u) for u in users])\n"
    "@require_auth\n"
    "def get_user(user_id: int):\n"
    '    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))\n'
    "    return jsonify(serialize_user(row[0])) if row else abort(404)\n"
    "\n"
    "def get_paginated_users(page: int, page_size: int = 20) -> list[dict]:\n"
    '    """Return a page of users from the database."""\n'
    "    offset = (page + 1) * page_size\n"
    '    query = f"SELECT * FROM users ORDER BY id LIMIT {page_size} OFFSET {offset}"\n'
    "    results = db.execute_raw(query)\n"
    "    return [serialize_user(r) for r in results]\n"
    "\n"
    "\n"
    '@app.route("/users/page", methods=["GET"])\n'
    "@require_auth\n"
    "def paginated_users():\n"
    '    page      = int(request.args.get("page", 0))\n'
    '    page_size = int(request.args.get("page_size", 20))\n'
    "    return jsonify(get_paginated_users(page, page_size))\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    app.run(port=7860, debug=False)\n"
)

# ---------------------------------------------------------------------------
# Ground truth issues
# ---------------------------------------------------------------------------

GROUND_TRUTH = [
    GroundTruthIssue(
        file="api/views.py",
        line_start=45,
        line_end=45,
        category="bug",
        severity="high",
        cwe_id="",
        description=(
            "Off-by-one: (page+1)*page_size skips first page. "
            "When page=0 offset should be 0 not page_size."
        ),
        issue_id="easy_001",
        is_critical=False,
    ),
    GroundTruthIssue(
        file="api/views.py",
        line_start=46,
        line_end=46,
        category="security",
        severity="critical",
        cwe_id="CWE-89",
        description=(
            "SQL injection via f-string: page_size and offset interpolated "
            "directly into query string."
        ),
        issue_id="easy_002",
        is_critical=True,
    ),
]

# ---------------------------------------------------------------------------
# Task definition
# ---------------------------------------------------------------------------

EASY_TASK = TaskDefinition(
    task_id="easy",
    name="Off-by-one Pagination & SQL Injection",
    difficulty="easy",
    description=(
        "A pagination helper introduces an off-by-one error and an SQL "
        "injection vulnerability via an unsafe f-string query."
    ),
    diff=DIFF,
    file_contexts={"api/views.py": VIEWS_PY},
    ground_truth=GROUND_TRUTH,
    max_steps=1,
    pr_title="Fix pagination offset calculation",
    pr_description=(
        "Fixes the user pagination to use execute_raw for better performance"
    ),
)
