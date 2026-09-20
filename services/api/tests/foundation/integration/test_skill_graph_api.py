"""Skill graph API: prerequisites, cycle rejection, levels, and permissions."""

import pytest

from tests.foundation.conftest import API, auth, make_competency, make_org, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def tenant(db_session):
    """A fresh tenant per test so edge changes never leak between tests."""
    org = make_org(db_session)
    ld = make_user(db_session, org, ["ld_admin"])
    learner = make_user(db_session, org, ["learner"])
    comps = {
        name: make_competency(db_session, org, f"sql.{name}", domain="sql")
        for name in ("basics", "filtering", "joins", "aggregation")
    }
    db_session.commit()
    return org, ld, learner, comps


async def add(client, user, competency, prerequisite, **extra):
    return await client.post(
        f"{API}/competencies/{competency.id}/prerequisites",
        json={"prerequisite_id": str(prerequisite.id), **extra},
        headers=auth(user),
    )


async def test_ld_admin_can_add_prerequisite(client, tenant):
    _, ld, _, c = tenant
    resp = await add(client, ld, c["filtering"], c["basics"], min_mastery=0.7, rationale="WHERE needs table basics")
    assert resp.status_code == 201
    body = resp.json()
    assert body["competency_id"] == str(c["filtering"].id)
    assert body["prerequisite_id"] == str(c["basics"].id)
    assert body["min_mastery"] == 0.7


async def test_learner_cannot_add_prerequisite(client, tenant):
    _, _, learner, c = tenant
    resp = await add(client, learner, c["joins"], c["filtering"])
    assert resp.status_code == 403


async def test_learner_can_read_the_graph(client, tenant):
    _, ld, learner, c = tenant
    await add(client, ld, c["joins"], c["filtering"])
    resp = await client.get(f"{API}/competencies/graph", headers=auth(learner))
    assert resp.status_code == 200
    assert len(resp.json()["edges"]) == 1


async def test_self_prerequisite_is_rejected(client, tenant):
    _, ld, _, c = tenant
    resp = await add(client, ld, c["basics"], c["basics"])
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "self_prerequisite"


async def test_duplicate_prerequisite_is_rejected(client, tenant):
    _, ld, _, c = tenant
    assert (await add(client, ld, c["joins"], c["filtering"])).status_code == 201
    resp = await add(client, ld, c["joins"], c["filtering"])
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "duplicate_prerequisite"


async def test_direct_cycle_is_rejected_with_the_offending_path(client, tenant):
    _, ld, _, c = tenant
    assert (await add(client, ld, c["joins"], c["filtering"])).status_code == 201
    resp = await add(client, ld, c["filtering"], c["joins"])  # would close filtering <-> joins
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "prerequisite_cycle"
    assert detail["cycle"][0] == detail["cycle"][-1]
    assert {str(c["filtering"].id), str(c["joins"].id)} <= set(detail["cycle"])


async def test_indirect_cycle_is_rejected(client, tenant):
    _, ld, _, c = tenant
    assert (await add(client, ld, c["filtering"], c["basics"])).status_code == 201
    assert (await add(client, ld, c["joins"], c["filtering"])).status_code == 201
    resp = await add(client, ld, c["basics"], c["joins"])  # basics -> joins -> filtering -> basics
    assert resp.status_code == 409
    assert len(resp.json()["detail"]["cycle"]) == 4  # a -> c -> b -> a


async def test_rejected_cycle_leaves_the_graph_unchanged(client, tenant):
    _, ld, _, c = tenant
    await add(client, ld, c["joins"], c["filtering"])
    await add(client, ld, c["filtering"], c["joins"])  # rejected
    graph = (await client.get(f"{API}/competencies/graph", headers=auth(ld))).json()
    assert len(graph["edges"]) == 1


async def test_graph_levels_follow_the_prerequisite_chain(client, tenant):
    _, ld, _, c = tenant
    await add(client, ld, c["filtering"], c["basics"])
    await add(client, ld, c["joins"], c["filtering"])
    await add(client, ld, c["aggregation"], c["joins"])
    graph = (await client.get(f"{API}/competencies/graph", headers=auth(ld))).json()
    level = {n["code"]: n["level"] for n in graph["nodes"]}
    assert level == {"sql.basics": 0, "sql.filtering": 1, "sql.joins": 2, "sql.aggregation": 3}
    assert graph["max_level"] == 3
    assert graph["domains"] == ["sql"]
    joins = next(n for n in graph["nodes"] if n["code"] == "sql.joins")
    assert joins["prerequisite_ids"] == [str(c["filtering"].id)]
    assert joins["dependent_ids"] == [str(c["aggregation"].id)]


async def test_list_prerequisites_direct_and_transitive(client, tenant):
    _, ld, _, c = tenant
    await add(client, ld, c["filtering"], c["basics"])
    await add(client, ld, c["joins"], c["filtering"])
    url = f"{API}/competencies/{c['joins'].id}/prerequisites"
    direct = (await client.get(url, headers=auth(ld))).json()
    assert [e["prerequisite_id"] for e in direct] == [str(c["filtering"].id)]
    transitive = (await client.get(url, params={"transitive": "true"}, headers=auth(ld))).json()
    assert {e["prerequisite_id"] for e in transitive} == {str(c["filtering"].id), str(c["basics"].id)}


async def test_remove_prerequisite(client, tenant):
    _, ld, _, c = tenant
    await add(client, ld, c["joins"], c["filtering"])
    url = f"{API}/competencies/{c['joins'].id}/prerequisites/{c['filtering'].id}"
    assert (await client.delete(url, headers=auth(ld))).status_code == 204
    assert (await client.delete(url, headers=auth(ld))).status_code == 404  # already gone
    # and the previously-blocked reverse edge is now legal
    assert (await add(client, ld, c["filtering"], c["joins"])).status_code == 201


async def test_learner_cannot_remove_prerequisite(client, tenant):
    _, ld, learner, c = tenant
    await add(client, ld, c["joins"], c["filtering"])
    url = f"{API}/competencies/{c['joins'].id}/prerequisites/{c['filtering'].id}"
    assert (await client.delete(url, headers=auth(learner))).status_code == 403


async def test_min_mastery_must_be_a_probability(client, tenant):
    _, ld, _, c = tenant
    resp = await add(client, ld, c["joins"], c["filtering"], min_mastery=1.5)
    assert resp.status_code == 422


async def test_unknown_competency_is_404(client, tenant):
    import uuid

    _, ld, _, c = tenant
    resp = await client.post(
        f"{API}/competencies/{c['joins'].id}/prerequisites",
        json={"prerequisite_id": str(uuid.uuid4())},
        headers=auth(ld),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "competency_not_found"


async def test_graph_route_is_not_shadowed_by_competency_id_route(client, tenant):
    _, ld, _, _ = tenant
    resp = await client.get(f"{API}/competencies/graph", headers=auth(ld))
    assert resp.status_code == 200  # would be 422 if "/competencies/{id}" matched "graph"


async def test_competency_crud_persists_domain_difficulty_and_metadata(client, tenant):
    _, ld, _, _ = tenant
    created = await client.post(
        f"{API}/competencies",
        json={"name": "Window Functions", "code": "sql.window", "domain": "sql", "difficulty": 0.7,
              "taxonomy_level": "analyze", "competency_metadata": {"source": "curriculum-2026"}},
        headers=auth(ld),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["domain"], body["difficulty"], body["competency_metadata"]) == ("sql", 0.7, {"source": "curriculum-2026"})

    updated = await client.put(f"{API}/competencies/{body['id']}", json={"difficulty": 0.8}, headers=auth(ld))
    assert updated.status_code == 200 and updated.json()["difficulty"] == 0.8

    bad = await client.put(f"{API}/competencies/{body['id']}", json={"difficulty": 2}, headers=auth(ld))
    assert bad.status_code == 422
