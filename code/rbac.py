"""
SUNLIGHT Role-Based Access Control
====================================

Roles: viewer, analyst, admin
Permissions scoped to tenant. Every endpoint checks role.

Role capabilities:
- viewer:  read scores, reports, dashboard (no write)
- analyst: viewer + submit contracts, run scans, export, disposition
- admin:   analyst + manage users, keys, tenants, webhooks, settings
"""

import os
import sys
from typing import Set, Optional, Dict
from functools import wraps

from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger

logger = get_logger("rbac")

# ---------------------------------------------------------------------------
# Role hierarchy
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "viewer": {
        "scores:read", "contracts:read", "reports:read",
        "dashboard:read", "runs:read", "audit:read",
        "jobs:read",
    },
    "analyst": {
        "scores:read", "contracts:read", "reports:read",
        "dashboard:read", "runs:read", "audit:read",
        "jobs:read",
        "contracts:write", "scan:submit", "reports:export",
        "disposition:write", "ingest:write", "jobs:write",
    },
    "admin": {
        "scores:read", "contracts:read", "reports:read",
        "dashboard:read", "runs:read", "audit:read",
        "jobs:read",
        "contracts:write", "scan:submit", "reports:export",
        "disposition:write", "ingest:write", "jobs:write",
        "users:manage", "keys:manage", "tenants:manage",
        "webhooks:manage", "settings:manage", "admin:read",
        "dlq:manage",
    },
}


def has_permission(role: str, permission: str) -> bool:
    """Check if role has a specific permission."""
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def require_permission(role: str, permission: str, tenant_id: str = ""):
    """Raise 403 if role lacks the required permission."""
    if not has_permission(role, permission):
        logger.warning("Authorization denied",
                       extra={"role": role, "permission": permission,
                              "tenant_id": tenant_id})
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' lacks permission '{permission}'",
        )


def require_role(minimum_role: str):
    """
    Check that the current role meets minimum level.
    Hierarchy: admin > analyst > viewer
    """
    hierarchy = {"viewer": 0, "analyst": 1, "admin": 2}

    def checker(current_role: str, tenant_id: str = ""):
        current_level = hierarchy.get(current_role, -1)
        required_level = hierarchy.get(minimum_role, 99)
        if current_level < required_level:
            logger.warning("Insufficient role",
                           extra={"current": current_role,
                                  "required": minimum_role,
                                  "tenant_id": tenant_id})
            raise HTTPException(
                status_code=403,
                detail=f"Requires role '{minimum_role}' or higher",
            )

    return checker


# ---------------------------------------------------------------------------
# Auth context helpers (used by API endpoints)
# ---------------------------------------------------------------------------

def get_role_from_key(key_record: Dict) -> str:
    """Extract role from API key record, defaulting to analyst."""
    scopes = key_record.get("scopes", "read,analyze")
    if "admin" in scopes:
        return "admin"
    elif "analyze" in scopes:
        return "analyst"
    return "viewer"


def check_tenant_access(key_tenant_id: str, requested_tenant_id: str):
    """Ensure API key's tenant matches the requested tenant."""
    if key_tenant_id != requested_tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Cross-tenant access denied",
        )
