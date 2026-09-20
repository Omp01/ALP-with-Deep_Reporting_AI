"""
Role vocabulary and pure permission logic.

The platform defines five canonical roles (spec §36):

    learner      own learning data
    manager      team data
    ld_admin     learning-programme and content data
    org_admin    organisation-level data
    super_admin  platform-level administration

The original codebase stored two of these under different names
(`instructor` for ld_admin, `system_admin` for super_admin). Those names are
still stored in `users.role` — 48 call sites compare against them — so this
module treats them as aliases. Every check goes through `normalize_role`, which
means a guard written as `["instructor", "org_admin"]` and one written as
`["ld_admin", "org_admin"]` behave identically.

This module is pure (no database, no FastAPI) so it can be unit tested in
isolation. The database-backed lookup lives in `app.api.deps`.
"""

from enum import Enum
from typing import Iterable, Optional, Set


class Role(str, Enum):
    LEARNER = "learner"
    MANAGER = "manager"
    LD_ADMIN = "ld_admin"
    ORG_ADMIN = "org_admin"
    SUPER_ADMIN = "super_admin"


# Legacy spellings accepted anywhere a role is read.
LEGACY_ALIASES = {
    "instructor": Role.LD_ADMIN,
    "system_admin": Role.SUPER_ADMIN,
}

# What `users.role` (the compatibility column) stores for each canonical role.
# Kept so existing `== "system_admin"` / `"instructor"` checks keep working.
LEGACY_STORAGE = {
    Role.LEARNER: "learner",
    Role.MANAGER: "manager",
    Role.LD_ADMIN: "instructor",
    Role.ORG_ADMIN: "org_admin",
    Role.SUPER_ADMIN: "system_admin",
}

# Higher = more privileged. Used only to pick a user's *primary* role for the
# compatibility column; it is NOT used for permission checks (roles do not
# inherit — a manager is not implicitly a learner).
ROLE_RANK = {
    Role.LEARNER: 10,
    Role.MANAGER: 20,
    Role.LD_ADMIN: 30,
    Role.ORG_ADMIN: 40,
    Role.SUPER_ADMIN: 50,
}

ROLE_LABELS = {
    Role.LEARNER: "Learner",
    Role.MANAGER: "Manager",
    Role.LD_ADMIN: "L&D Admin",
    Role.ORG_ADMIN: "Organization Admin",
    Role.SUPER_ADMIN: "Super Admin",
}

ROLE_DESCRIPTIONS = {
    Role.LEARNER: "Consumes learning content and sees their own learning data.",
    Role.MANAGER: "Sees learning data and skill gaps for the teams they manage.",
    Role.LD_ADMIN: "Owns learning programmes: content, courses, competencies and assessments.",
    Role.ORG_ADMIN: "Administers the organisation: users, roles and organisation-level reporting.",
    Role.SUPER_ADMIN: "Platform-level administration across organisations.",
}


def normalize_role(value: "Optional[str | Role]") -> Optional[Role]:
    """Map any accepted spelling of a role to a canonical `Role`, or None if unknown."""
    if value is None:
        return None
    if isinstance(value, Role):
        return value
    text = str(value).strip().lower()
    if text in LEGACY_ALIASES:
        return LEGACY_ALIASES[text]
    try:
        return Role(text)
    except ValueError:
        return None


def normalize_roles(values: "Iterable[str | Role]") -> Set[Role]:
    """Normalise a collection of roles, dropping anything unrecognised."""
    result: Set[Role] = set()
    for value in values:
        role = normalize_role(value)
        if role is not None:
            result.add(role)
    return result


def has_any_role(held: "Iterable[str | Role]", allowed: "Iterable[str | Role]") -> bool:
    """True when the user holds at least one allowed role. `super_admin` always passes."""
    held_set = normalize_roles(held)
    if Role.SUPER_ADMIN in held_set:
        return True
    return bool(held_set & normalize_roles(allowed))


def primary_role(roles: "Iterable[str | Role]") -> Optional[Role]:
    """The most privileged of the given roles, or None when the set is empty."""
    role_set = normalize_roles(roles)
    if not role_set:
        return None
    return max(role_set, key=lambda r: ROLE_RANK[r])


def legacy_storage_value(roles: "Iterable[str | Role]") -> Optional[str]:
    """The value to write into the compatibility column `users.role`."""
    primary = primary_role(roles)
    return LEGACY_STORAGE[primary] if primary else None
