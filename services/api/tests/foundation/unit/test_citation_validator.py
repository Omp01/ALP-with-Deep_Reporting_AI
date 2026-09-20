"""
Citation validation (app/reporting/validator.py): what stops a reporting model from inventing evidence, numbers or causation.
"""

import pytest

from app.reporting import validator as v
from app.reporting.package import Package, evidence_confidence
from datetime import datetime, timedelta
from uuid import uuid4

ORG = uuid4()
LEARNER = uuid4()
NOW = datetime(2026, 9, 20, 12, 0)


@pytest.fixture
def pkg():
    p = Package(ORG, "learner", "learner", LEARNER, "Alice", NOW - timedelta(days=30), NOW)
    p.record("state", "s1", "SQL Joins state", {"competency": "SQL Joins", "mastery": 0.42, "target": 0.7, "evidence_count": 6}, NOW, LEARNER)
    p.record("evidence", "e1", "answer", {"signal": 0.0, "error_type": "conceptual_misunderstanding"}, NOW - timedelta(days=2), LEARNER)
    p.record("evidence", "old", "answer", {"signal": 1.0}, NOW - timedelta(days=90), LEARNER)
    p.record("evidence", "other", "answer", {"signal": 1.0}, NOW - timedelta(days=1), uuid4())
    p.metric("joins_mastery", "SQL Joins: mastery", 0.42, "probability", "Current estimate", ["state_s1"])
    p.metric("joins_wrong", "Incorrect answers", 3, "answers", "Signal below 0.5")
    return p


def check(pkg, **claim):
    base = {"claim": "SQL Joins is at 42%.", "claim_type": "OBSERVATION", "evidence_ids": ["state_s1"], "metric_ids": ["metric_joins_mastery"]}
    return v.validate_claim({**base, **claim}, pkg.to_dict(), str(ORG))


def test_a_claim_with_real_evidence_and_matching_numbers_is_accepted(pkg):
    result = check(pkg)
    assert result["status"] == "accepted" and result["flags"] == []


@pytest.mark.parametrize("text", ["SQL Joins is at 42%.", "SQL Joins mastery is 0.42.", "SQL Joins is at 42 percent of the way.", "It stands at 0.4."])
def test_numbers_may_appear_as_a_fraction_a_percentage_or_rounded(pkg, text):
    assert check(pkg, claim=text)["status"] == "accepted"


def test_a_number_that_is_not_in_the_cited_evidence_is_rejected(pkg):
    result = check(pkg, claim="SQL Joins is at 68%.")
    assert result["status"] == "rejected" and any("68" in f for f in result["flags"])


def test_a_number_from_uncited_evidence_does_not_count(pkg):
    result = check(pkg, claim="There were 3 incorrect answers.", metric_ids=["metric_joins_mastery"])
    assert result["status"] == "rejected"
    assert check(pkg, claim="There were 3 incorrect answers.", metric_ids=["metric_joins_wrong"])["status"] == "accepted"


def test_a_claim_without_evidence_is_rejected(pkg):
    result = check(pkg, evidence_ids=[])
    assert result["status"] == "rejected" and "no evidence is cited" in result["flags"]


def test_an_invented_evidence_id_is_rejected(pkg):
    result = check(pkg, evidence_ids=["evidence_made_up"])
    assert result["status"] == "rejected" and any("does not exist" in f for f in result["flags"])


def test_an_invented_metric_id_is_rejected(pkg):
    assert check(pkg, metric_ids=["metric_nope"])["status"] == "rejected"


def test_evidence_from_another_tenant_is_rejected_even_if_it_is_in_the_package(pkg):
    pkg.records["evidence_e1"]["org_id"] = str(uuid4())
    result = check(pkg, evidence_ids=["evidence_e1"], claim="An answer was incorrect.")
    assert result["status"] == "rejected" and any("another tenant" in f for f in result["flags"])


def test_a_learner_report_cannot_cite_another_learners_record(pkg):
    result = check(pkg, evidence_ids=["evidence_other"], claim="An answer was correct.", metric_ids=[])
    assert result["status"] == "rejected" and any("different learner" in f for f in result["flags"])


def test_evidence_outside_the_period_is_rejected(pkg):
    result = check(pkg, evidence_ids=["evidence_old"], claim="An answer was correct.", metric_ids=[])
    assert result["status"] == "rejected" and any("outside the report period" in f for f in result["flags"])


def test_a_causal_claim_is_rejected_because_the_platform_has_no_causal_evidence(pkg):
    result = check(pkg, claim_type="CAUSAL_CLAIM", claim="The video improved mastery.")
    assert result["status"] == "rejected" and any("causal" in f for f in result["flags"])


@pytest.mark.parametrize("text", ["SQL Joins fell to 42% because of the video.", "The lesson led to a mastery of 42%.", "Mastery is 42% as a result of the quiz.", "Retries caused 42% mastery."])
def test_causal_wording_in_an_observation_is_rejected(pkg, text):
    result = check(pkg, claim=text)
    assert result["status"] == "rejected" and any("causation" in f for f in result["flags"])


def test_saying_that_causation_is_not_established_is_the_right_wording(pkg):
    result = check(pkg, claim_type="CORRELATION", claim="SQL Joins is at 42%. This does not establish that the video caused it.")
    assert result["status"] == "accepted"


def test_an_unknown_claim_type_is_rejected(pkg):
    assert check(pkg, claim_type="FACT")["status"] == "rejected"


def test_an_empty_claim_is_rejected(pkg):
    assert check(pkg, claim="  ")["status"] == "rejected"


def test_a_recommendation_still_needs_evidence_but_may_use_possibility_language(pkg):
    result = check(pkg, claim_type="PLAUSIBLE_EXPLANATION", claim="Revisiting joins may help, given SQL Joins is at 42%.")
    assert result["status"] == "accepted"


def test_validate_all_separates_accepted_from_rejected(pkg):
    out = v.validate_all([{"claim": "SQL Joins is at 42%.", "claim_type": "OBSERVATION", "evidence_ids": ["state_s1"], "metric_ids": ["metric_joins_mastery"]},
                          {"claim": "Everyone is at 99%.", "claim_type": "OBSERVATION", "evidence_ids": ["state_s1"], "metric_ids": []}], pkg.to_dict(), str(ORG))
    assert len(out["accepted"]) == 1 and len(out["rejected"]) == 1 and out["rejected"][0]["flags"]


def test_a_narrative_is_held_to_the_same_numbers_and_wording(pkg):
    assert v.validate_narrative("SQL Joins is at 42% with 3 incorrect answers.", pkg.to_dict()) == []
    assert v.validate_narrative("Mastery is 91%.", pkg.to_dict())
    assert v.validate_narrative("Mastery is 42% because of the video.", pkg.to_dict()) == ["causal wording"]


def test_package_ids_are_typed_and_the_hash_ignores_the_period(pkg):
    assert set(pkg.records) >= {"state_s1", "evidence_e1"} and set(pkg.metrics) == {"metric_joins_mastery", "metric_joins_wrong"}
    other = Package(ORG, "learner", "learner", LEARNER, "Alice", NOW - timedelta(days=7), NOW)
    other.records, other.metrics = dict(pkg.records), dict(pkg.metrics)
    assert other.content_hash() == pkg.content_hash()
    other.metric("extra", "x", 1, "n", "d")
    assert other.content_hash() != pkg.content_hash()


def test_evidence_confidence_is_volume_not_truth():
    assert evidence_confidence(0) == 0.0 and evidence_confidence(3) == 0.5 and evidence_confidence(9) == 0.75


def test_the_model_sees_the_findings_and_the_records_they_cite_and_nothing_else(pkg):
    pkg.pattern("weak", "SQL Joins is at 42%.", ["metric_joins_mastery"], ["state_s1", "evidence_missing"], subject="SQL Joins")
    compact = pkg.compact()
    assert set(compact["records"]) == {"state_s1"} and compact["patterns"][0]["evidence_ids"] == ["state_s1"]
