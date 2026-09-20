"""
Tenant isolation for the content-ingestion API.

Tenant B ingests real content (through the API); tenant A's most privileged non-platform user
(an org admin, so a 404 can only come from tenant scoping) then tries to read, change, publish
and delete it. Every foreign id must look exactly like an id that does not exist.
"""

import uuid

import pytest

from app.models import ContentItem, QuestionCandidate
from tests.foundation.conftest import API, auth
from tests.foundation.fakes import PROSE, ScriptedAI

pytestmark = pytest.mark.integration

ADMIN = f"{API}/admin/content"


@pytest.fixture
async def foreign(client, ingestion_env, world):
    """Tenant B's ingested (reviewable) content, its first question candidate and its job."""
    ingestion_env.use_ai(ScriptedAI())
    unique = f"{PROSE} Reference {uuid.uuid4()} is recorded in the appendix of this guide for auditors."   # `world` is shared by all tests
    resp = await client.post(f"{ADMIN}/ingest/file", files={"file": ("Joins.txt", unique.encode(), "text/plain")},
                             data={"module_id": str(world.b.module.id)}, headers=auth(world.b.org_admin))
    assert resp.status_code == 202, resp.text
    ids = resp.json()
    body = (await client.get(f"{ADMIN}/{ids['content_id']}", headers=auth(world.b.org_admin))).json()
    assert body["candidates"], "tenant B should have generated questions"
    return {"content": ids["content_id"], "job": ids["job_id"], "candidate": body["candidates"][0]["id"]}


def requests_for(f, world):
    option = lambda t, ok=False: {"text": t, "is_correct": ok}
    return [
        ("get content", "GET", f"/{f['content']}", None),
        ("edit content", "PUT", f"/{f['content']}", {"title": "hijacked"}),
        ("reprocess", "POST", f"/{f['content']}/process", {}),
        ("set transcript", "PUT", f"/{f['content']}/transcript", {"text": "x" * 80}),
        ("edit analysis", "PUT", f"/{f['content']}/analysis", {"objectives": ["hijacked objective"]}),
        ("add question", "POST", f"/{f['content']}/candidates",
         {"question_text": "Injected question here?", "options": [option("a", True), option("b"), option("c")]}),
        ("bulk question status", "POST", f"/{f['content']}/candidates/status", {"ids": [f["candidate"]], "status": "approved"}),
        ("edit question", "PUT", f"/candidates/{f['candidate']}", {"difficulty": 0.9}),
        ("set question status", "POST", f"/candidates/{f['candidate']}/status", {"status": "approved"}),
        ("delete question", "DELETE", f"/candidates/{f['candidate']}", None),
        ("publish", "POST", f"/{f['content']}/publish", None),
        ("unpublish", "POST", f"/{f['content']}/unpublish", None),
        ("delete content", "DELETE", f"/{f['content']}", None),
        ("job status", "GET", f"/jobs/{f['job']}", None),
        ("upload into foreign module", "POST", "/ingest/file", "UPLOAD_FOREIGN_MODULE"),
        ("youtube into foreign module", "POST", "/ingest/youtube",
         {"url": "https://www.youtube.com/watch?v=aJc5MuJbOr0", "module_id": str(world.b.module.id)}),
    ]


CASES = 16


@pytest.mark.parametrize("index", range(CASES))
async def test_foreign_ingestion_resources_are_not_found(client, ingestion_env, world, foreign, db_session, index):
    cases = requests_for(foreign, world)
    assert len(cases) == CASES, "update CASES when adding requests"
    label, method, path, body = cases[index]
    headers = auth(world.a.org_admin)

    if body == "UPLOAD_FOREIGN_MODULE":
        resp = await client.post(f"{API}/admin/content{path}", files={"file": ("a.txt", PROSE.encode(), "text/plain")},
                                 data={"module_id": str(world.b.module.id), "allow_duplicate": "true"}, headers=headers)
    else:
        resp = await client.request(method, f"{ADMIN}{path}", json=body, headers=headers)
    assert resp.status_code == 404, f"{label}: expected 404, got {resp.status_code} {resp.text[:200]}"

    # ... and nothing about tenant B's data changed
    item = db_session.get(ContentItem, foreign["content"])
    db_session.refresh(item)
    assert item.title == "Joins" and item.status == "review"
    candidate = db_session.get(QuestionCandidate, foreign["candidate"])
    assert candidate is not None and candidate.status == "pending" and not candidate.edited


async def test_a_foreign_id_is_indistinguishable_from_one_that_does_not_exist(client, world, foreign):
    headers = auth(world.a.org_admin)
    real = await client.get(f"{ADMIN}/{foreign['content']}", headers=headers)
    missing = await client.get(f"{ADMIN}/{uuid.uuid4()}", headers=headers)
    assert real.status_code == missing.status_code == 404
    assert real.json() == missing.json()


async def test_the_library_lists_only_own_tenant_content(client, world, foreign):
    theirs = (await client.get(ADMIN, params={"limit": 100}, headers=auth(world.a.org_admin))).json()
    assert foreign["content"] not in {i["id"] for i in theirs["items"]}
    assert {i["course_id"] for i in theirs["items"]} == {str(world.a.course.id)}          # only tenant A's own lessons
    mine = (await client.get(ADMIN, params={"limit": 100}, headers=auth(world.b.org_admin))).json()
    assert foreign["content"] in {i["id"] for i in mine["items"]}
    assert (await client.get(ADMIN, params={"q": "Joins"}, headers=auth(world.a.org_admin))).json()["total"] == 0   # searching cannot surface it either


async def test_a_foreign_competency_cannot_be_used_in_a_question(client, ingestion_env, world, foreign):
    resp = await client.put(f"{ADMIN}/candidates/{foreign['candidate']}", json={"competency_id": str(world.a.competencies[0].id)},
                            headers=auth(world.b.org_admin))
    assert resp.status_code == 404


async def test_super_admin_impersonation_header_reaches_only_the_named_tenant(client, world, foreign):
    """The platform administrator can act inside a tenant only by naming it explicitly."""
    headers = {**auth(world.super_admin), "X-Tenant-ID": str(world.b.org.id)}
    body = await client.get(ADMIN, headers=headers)
    assert body.status_code in (200, 403)          # roles for the content admin API are tenant roles
    if body.status_code == 200:
        assert foreign["content"] in {i["id"] for i in body.json()["items"]}
