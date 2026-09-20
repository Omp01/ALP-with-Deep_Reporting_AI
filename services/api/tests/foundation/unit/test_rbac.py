"""Pure tests for the role vocabulary and permission logic."""

import pytest

from app.core.rbac import (
    Role,
    has_any_role,
    legacy_storage_value,
    normalize_role,
    normalize_roles,
    primary_role,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("learner", Role.LEARNER),
        ("manager", Role.MANAGER),
        ("ld_admin", Role.LD_ADMIN),
        ("org_admin", Role.ORG_ADMIN),
        ("super_admin", Role.SUPER_ADMIN),
        # legacy spellings still stored in users.role
        ("instructor", Role.LD_ADMIN),
        ("system_admin", Role.SUPER_ADMIN),
        # tolerant of case and whitespace
        ("  Instructor ", Role.LD_ADMIN),
        ("ORG_ADMIN", Role.ORG_ADMIN),
    ],
)
def test_normalize_role_accepts_canonical_and_legacy(raw, expected):
    assert normalize_role(raw) is expected


@pytest.mark.parametrize("raw", [None, "", "admin", "root", "teacher"])
def test_normalize_role_rejects_unknown(raw):
    assert normalize_role(raw) is None


def test_normalize_roles_drops_unknown_and_dedupes():
    assert normalize_roles(["instructor", "ld_admin", "nonsense"]) == {Role.LD_ADMIN}


def test_legacy_and_canonical_spellings_are_interchangeable_in_guards():
    assert has_any_role(["instructor"], ["ld_admin"])
    assert has_any_role(["ld_admin"], ["instructor"])
    assert has_any_role(["system_admin"], ["super_admin"])


def test_super_admin_passes_every_guard():
    assert has_any_role([Role.SUPER_ADMIN], ["learner"])
    assert has_any_role(["system_admin"], [])


def test_roles_do_not_inherit():
    # A manager is not implicitly a learner, and an org admin is not implicitly an L&D admin.
    assert not has_any_role(["manager"], ["learner"])
    assert not has_any_role(["org_admin"], ["ld_admin"])
    assert not has_any_role(["learner"], ["manager", "ld_admin", "org_admin"])


def test_user_with_no_roles_passes_nothing():
    assert not has_any_role([], ["learner"])


def test_primary_role_is_most_privileged():
    assert primary_role(["learner", "manager"]) is Role.MANAGER
    assert primary_role(["manager", "org_admin", "learner"]) is Role.ORG_ADMIN
    assert primary_role([]) is None


@pytest.mark.parametrize(
    "roles, stored",
    [
        (["learner"], "learner"),
        (["ld_admin"], "instructor"),          # compatibility column keeps the legacy spelling
        (["super_admin"], "system_admin"),
        (["learner", "manager"], "manager"),
        ([], None),
    ],
)
def test_legacy_storage_value(roles, stored):
    assert legacy_storage_value(roles) == stored
