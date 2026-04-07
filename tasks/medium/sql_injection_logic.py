"""
tasks/medium/sql_injection_logic.py — Medium task: auth bypass + SSRF.
"""

from __future__ import annotations

from code_review_env.models import GroundTruthIssue
from code_review_env.tasks.base_task import TaskDefinition

# ---------------------------------------------------------------------------
# Unified diff (2 files)
# ---------------------------------------------------------------------------

DIFF = """\
--- a/auth/token_validator.py
+++ b/auth/token_validator.py
@@ -15,12 +15,14 @@
 import jwt
+import time
 
 class TokenValidator:
     def __init__(self, secret_key: str, algorithm: str = "HS256"):
         self.secret_key = secret_key
         self.algorithm = algorithm
 
-    def validate(self, token: str) -> dict:
+    def validate(self, token: str, verify_exp: bool = True) -> dict:
         try:
-            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
+            payload = jwt.decode(
+                token, self.secret_key,
+                algorithms=[self.algorithm],
+                options={"verify_exp": verify_exp}
+            )
+            if payload.get("role") == "admin" or payload.get("role") == "superadmin":
+                payload["is_privileged"] = True
             return payload
         except jwt.ExpiredSignatureError:
             raise ValueError("Token expired")
-        except jwt.InvalidTokenError:
+        except jwt.InvalidTokenError as e:
+            if "expired" in str(e).lower():
+                raise ValueError("Token expired")
             raise ValueError("Invalid token")

--- a/users/profile.py
+++ b/users/profile.py
@@ -8,10 +8,15 @@
 import requests
+from urllib.parse import urlparse
 
 class ProfileService:
-    def update_avatar(self, user_id: int, image_data: bytes) -> str:
-        \"\"\"Upload avatar image and return URL.\"\"\"
-        path = f"/avatars/{user_id}.png"
-        storage.save(path, image_data)
-        return f"https://cdn.example.com{path}"
+    def update_avatar(self, user_id: int, image_url: str) -> str:
+        \"\"\"Fetch avatar from URL and save it.\"\"\"
+        parsed = urlparse(image_url)
+        if parsed.scheme not in ("http", "https"):
+            raise ValueError("Invalid URL scheme")
+        response = requests.get(image_url, timeout=10)
+        response.raise_for_status()
+        path = f"/avatars/{user_id}.png"
+        storage.save(path, response.content)
+        return f"https://cdn.example.com{path}"
"""

# ---------------------------------------------------------------------------
# File contexts
# ---------------------------------------------------------------------------

# auth/token_validator.py
# validate() must start at line 21.  Layout:
#   1-14  : module docstring + imports + constants (14 lines)
#   15    : blank
#   16-20 : class TokenValidator + __init__ (5 lines)
#   21    : def validate(...)           ← ground truth origin
#   22-26 : try + jwt.decode block (verify_exp option)   ← issue med_001
#   27-28 : is_privileged block                          ← issue med_002
#   29    : return payload
#   30-31 : except ExpiredSignatureError
#   32-34 : except InvalidTokenError duplicate block      ← issue med_003

TOKEN_VALIDATOR_PY = """\
\"\"\"auth/token_validator.py — JWT validation for the authentication service.\"\"\"

from __future__ import annotations
import logging
from typing import Optional
import jwt

logger = logging.getLogger(__name__)
SUPPORTED_ALGORITHMS = ["HS256", "HS384", "HS512"]


class TokenValidator:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        if algorithm not in SUPPORTED_ALGORITHMS:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        self.secret_key = secret_key
        self.algorithm = algorithm
        self._cache: dict = {}

    def validate(self, token: str, verify_exp: bool = True) -> dict:
        try:
            payload = jwt.decode(
                token, self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": verify_exp}
            )
            if payload.get("role") == "admin" or payload.get("role") == "superadmin":
                payload["is_privileged"] = True
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError as e:
            if "expired" in str(e).lower():
                raise ValueError("Token expired")
            raise ValueError("Invalid token")

    def get_subject(self, token: str) -> Optional[str]:
        \"\"\"Return the 'sub' claim without full validation.\"\"\"
        try:
            unverified = jwt.decode(
                token, options={"verify_signature": False}
            )
            return unverified.get("sub")
        except Exception:
            return None

    def refresh_token(self, token: str, new_exp: int) -> str:
        \"\"\"Issue a refreshed token preserving all claims except expiry.\"\"\"
        payload = self.validate(token, verify_exp=False)
        payload["exp"] = new_exp
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def revoke(self, token: str) -> None:
        \"\"\"Mark a token as revoked in the in-memory cache.\"\"\"
        import hashlib
        key = hashlib.sha256(token.encode()).hexdigest()
        self._cache[key] = True

    def is_revoked(self, token: str) -> bool:
        import hashlib
        key = hashlib.sha256(token.encode()).hexdigest()
        return key in self._cache
"""

# users/profile.py
# update_avatar must start at line 10 → lines 14-19 are the SSRF block.
# Layout:
#   1-8  : docstring + imports (8 lines)
#   9    : blank
#   10   : class ProfileService:
#   11   : blank
#   12-13: def update_avatar header + docstring
#   14-19: SSRF body                                     ← issue med_004
#   20+  : rest of class

PROFILE_PY = """\
\"\"\"users/profile.py — Profile management service including avatar handling.\"\"\"

from __future__ import annotations

import logging
import requests
from urllib.parse import urlparse

from storage import storage

class ProfileService:

    def update_avatar(self, user_id: int, image_url: str) -> str:
        \"\"\"Fetch avatar from URL and save it.\"\"\"
        parsed = urlparse(image_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Invalid URL scheme")
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        path = f"/avatars/{user_id}.png"
        storage.save(path, response.content)
        return f"https://cdn.example.com{path}"

    def get_avatar_url(self, user_id: int) -> str:
        \"\"\"Return the CDN URL for a user's current avatar.\"\"\"
        return f"https://cdn.example.com/avatars/{user_id}.png"

    def delete_avatar(self, user_id: int) -> None:
        \"\"\"Remove a user's avatar from storage.\"\"\"
        path = f"/avatars/{user_id}.png"
        storage.delete(path)

    def update_display_name(self, user_id: int, name: str) -> dict:
        \"\"\"Update a user's display name and return the updated profile.\"\"\"
        if len(name) > 64:
            raise ValueError("Display name too long (max 64 chars)")
        from db import db
        db.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            (name, user_id)
        )
        return {"user_id": user_id, "display_name": name}

    def get_profile(self, user_id: int) -> dict:
        \"\"\"Return the full profile dict for a user.\"\"\"
        from db import db
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        if not row:
            raise LookupError(f"User {user_id} not found")
        return {
            "id":           row[0].id,
            "display_name": row[0].display_name,
            "avatar_url":   self.get_avatar_url(user_id),
        }
"""

# ---------------------------------------------------------------------------
# Ground truth issues
# ---------------------------------------------------------------------------

GROUND_TRUTH = [
    GroundTruthIssue(
        file="auth/token_validator.py",
        line_start=22,
        line_end=26,
        category="security",
        severity="critical",
        cwe_id="CWE-287",
        description=(
            "verify_exp parameter allows callers to bypass token expiration check"
        ),
        issue_id="med_001",
        is_critical=True,
    ),
    GroundTruthIssue(
        file="auth/token_validator.py",
        line_start=27,
        line_end=28,
        category="bug",
        severity="medium",
        cwe_id="",
        description=(
            "Privilege escalation: is_privileged set from unverified role claim in payload"
        ),
        issue_id="med_002",
        is_critical=False,
    ),
    GroundTruthIssue(
        file="auth/token_validator.py",
        line_start=32,
        line_end=34,
        category="style",
        severity="low",
        cwe_id="",
        description=(
            "Redundant exception handling duplicates ExpiredSignatureError catch above"
        ),
        issue_id="med_003",
        is_critical=False,
    ),
    GroundTruthIssue(
        file="users/profile.py",
        line_start=14,
        line_end=19,
        category="security",
        severity="critical",
        cwe_id="CWE-918",
        description=(
            "SSRF: scheme check insufficient, AWS metadata and internal network URLs not blocked"
        ),
        issue_id="med_004",
        is_critical=True,
    ),
]

# ---------------------------------------------------------------------------
# Task definition
# ---------------------------------------------------------------------------

MEDIUM_TASK = TaskDefinition(
    task_id="medium",
    name="Auth Bypass & SSRF in Profile Service",
    difficulty="medium",
    description=(
        "A token validator introduces an expiry-bypass parameter and "
        "unverified privilege escalation; the profile service adds an SSRF "
        "vulnerability via URL-based avatar fetching."
    ),
    diff=DIFF,
    file_contexts={
        "auth/token_validator.py": TOKEN_VALIDATOR_PY,
        "users/profile.py":        PROFILE_PY,
    },
    ground_truth=GROUND_TRUTH,
    max_steps=1,
    pr_title="Refactor auth service and add URL avatar upload",
    pr_description=(
        "Updates token validation to support optional expiry check, adds "
        "privilege detection, switches avatar upload to URL-based fetching"
    ),
)
