"""Shared auth model primitives for Step 1 architecture scaffolding.

RBAC and JWT implementation is added in Step 2.
"""

from enum import Enum


class Role(str, Enum):
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"
