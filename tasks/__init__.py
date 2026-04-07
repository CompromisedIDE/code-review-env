"""
tasks/__init__.py — Registers all task definitions with the global REGISTRY.

Import order matters: REGISTRY must exist before task modules are loaded.
"""

from code_review_env.tasks.base_task import TaskDefinition
from code_review_env.tasks.task_registry import REGISTRY

# Import task modules — their module-level EASY/MEDIUM/HARD_TASK constants
# are registered below.
from code_review_env.tasks.easy.off_by_one import EASY_TASK
from code_review_env.tasks.medium.sql_injection_logic import MEDIUM_TASK
from code_review_env.tasks.hard.payment_pr import HARD_TASK

REGISTRY.register(EASY_TASK)
REGISTRY.register(MEDIUM_TASK)
REGISTRY.register(HARD_TASK)

__all__ = ["TaskDefinition", "REGISTRY"]
