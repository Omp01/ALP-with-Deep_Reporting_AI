"""Role catalogue, role assignment rules, and legacy-vocabulary compatibility."""

import pytest

from app.models import AuditLog
from tests.foundation.conftest import API, auth, make_competency, make_org, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def tenant(db_session):
    org = make_org(db_session)
    people = {
        "learner": make_user(db_session, org, ["learner"]),
        "other_learner": make_user(db_session, org, ["learner"]),
        "manager": make_user(db_session, org, ["manager"]),
        "ld": make_user(db_session, org, ["ld_admin"]),
        "admin": make_user(db_session, org, ["org_admin"]),
    }
    db_session.commit()
    return org, people


async def test_role_catalogue_lists_five_roles_in_order(client, tenant):
    _, p = tenant
    resp = await client.get(f"{API}/roles", headers=auth(p["learner"]))
    assert resp.status_code == 200
    assert [r["code"] for r in resp.json()] == ["learner", "manager", "ld_admin", "org_admin", "super_admin"]


async def test_roles_require_authentication(client):
    assert (await client.get(f"{API}/roles")).status_code == 401


async def test_me_exposes_canonical_roles_and_legacy_role(client, tenant):
    _, p = tenant
    resp = await client.get(f"{API}/auth/me", headers=auth(p["ld"]))
    body = resp.json()
    assert body["roles"] == ["ld_admin"]
    assert body["role"] == "instructor"  # legacy spelling preserved for the existing frontend


async def test_org_admin_can_assign_roles(client, tenant, db_session):
    _, p = tenant
    resp = await client.put(
        f"{API}/users/{p['learner'].id}/roles", json={"roles": ["learner", "manager"]}, headers=auth(p["admin"])
    )
    assert resp.status_code == 200
    assert resp.json()["roles"] == ["learner", "manager"]

    me = (await client.get(f"{API}/auth/me", headers=auth(p["learner"]))).json()
    assert me["roles"] == ["manager", "learner"]  # most privileged first
    assert me["role"] == "manager"  # compatibility column follows the primary role

    audit = db_session.query(AuditLog).filter_by(action="USER_ROLES_CHANGED", resource_id=str(p["learner"].id)).one()
    assert audit.changes == {"before": ["learner"], "after": ["learner", "manager"]}


async def test_new_role_takes_effect_immediately_on_guarded_routes(client, tenant):
    _, p = tenant
    body = {"name": "Probe", "code": "probe.one"}
    assert (await client.post(f"{API}/competencies", json=body, headers=auth(p["learner"]))).status_code == 403
    await client.put(f"{API}/users/{p['learner'].id}/roles", json={"roles": ["ld_admin"]}, headers=auth(p["admin"]))
    assert (await client.post(f"{API}/competencies", json=body, headers=auth(p["learner"]))).status_code == 201


async def test_legacy_spelling_is_accepted_when_assigning(client, tenant):
    _, p = tenant
    resp = await client.put(
        f"{API}/users/{p['other_learner'].id}/roles", json={"roles": ["instructor"]}, headers=auth(p["admin"])
    )
    assert resp.status_code == 200 and resp.json()["roles"] == ["ld_admin"]


@pytest.mark.parametrize("who", ["learner", "manager", "ld"])
async def test_only_org_admins_can_change_roles(client, tenant, who):
    _, p = tenant
    resp = await client.put(
        f"{API}/users/{p['other_learner'].id}/roles", json={"roles": ["manager"]}, headers=auth(p[who])
    )
    assert resp.status_code == 403


async def test_nobody_can_change_their_own_roles(client, tenant):
    _, p = tenant
    resp = await client.put(f"{API}/users/{p['admin'].id}/roles", json={"roles": ["super_admin"]}, headers=auth(p["admin"]))
    assert resp.status_code == 403


async def test_org_admin_cannot_grant_super_admin(client, tenant):
    _, p = tenant
    resp = await client.put(
        f"{API}/users/{p['learner'].id}/roles", json={"roles": ["super_admin"]}, headers=auth(p["admin"])
    )
    assert resp.status_code == 403


async def test_org_admin_cannot_modify_an_existing_super_admin(client, tenant, db_session):
    org, p = tenant
    sup = make_user(db_session, org, ["super_admin"])
    db_session.commit()
    resp = await client.put(f"{API}/users/{sup.id}/roles", json={"roles": ["learner"]}, headers=auth(p["admin"]))
    assert resp.status_code == 403


async def test_super_admin_can_grant_super_admin(client, tenant, db_session):
    org, p = tenant
    sup = make_user(db_session, org, ["super_admin"])
    db_session.commit()
    resp = await client.put(f"{API}/users/{p['learner'].id}/roles", json={"roles": ["super_admin"]}, headers=auth(sup))
    assert resp.status_code == 200
    assert (await client.get(f"{API}/auth/me", headers=auth(p["learner"]))).json()["role"] == "system_admin"


async def test_unknown_role_is_rejected(client, tenant):
    _, p = tenant
    resp = await client.put(f"{API}/users/{p['learner'].id}/roles", json={"roles": ["wizard"]}, headers=auth(p["admin"]))
    assert resp.status_code == 400


async def test_a_user_must_keep_at_least_one_role(client, tenant):
    _, p = tenant
    resp = await client.put(f"{API}/users/{p['learner'].id}/roles", json={"roles": []}, headers=auth(p["admin"]))
    assert resp.status_code == 422


async def test_learner_can_read_only_their_own_roles(client, tenant):
    _, p = tenant
    own = await client.get(f"{API}/users/{p['learner'].id}/roles", headers=auth(p["learner"]))
    assert own.status_code == 200 and own.json()["roles"] == ["learner"]
    other = await client.get(f"{API}/users/{p['other_learner'].id}/roles", headers=auth(p["learner"]))
    assert other.status_code == 403


async def test_user_without_role_links_falls_back_to_legacy_column(client, db_session):
    """A user that predates the user_roles table must not lose access."""
    org = make_org(db_session)
    legacy_ld = make_user(db_session, org, [], set_role_links=False, legacy_role="instructor")
    db_session.commit()
    resp = await client.post(
        f"{API}/competencies", json={"name": "Legacy", "code": "legacy.one"}, headers=auth(legacy_ld)
    )
    assert resp.status_code == 201
    assert (await client.get(f"{API}/auth/me", headers=auth(legacy_ld))).json()["roles"] == ["ld_admin"]


async def test_role_filter_on_user_list_accepts_both_spellings(client, tenant):
    _, p = tenant
    for spelling in ("ld_admin", "instructor"):
        resp = await client.get(f"{API}/users", params={"role": spelling}, headers=auth(p["admin"]))
        assert resp.status_code == 200
        assert [u["id"] for u in resp.json()] == [str(p["ld"].id)]


async def test_learner_cannot_read_other_profiles(client, tenant):
    _, p = tenant
    assert (await client.get(f"{API}/users/{p['learner'].id}", headers=auth(p["learner"]))).status_code == 200
    assert (await client.get(f"{API}/users/{p['other_learner'].id}", headers=auth(p["learner"]))).status_code == 403
    assert (await client.get(f"{API}/users", headers=auth(p["learner"]))).status_code == 403
