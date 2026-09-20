"""
The skill-gap rules (app/competency/gaps.py) and the risk rules (app/competency/risk.py).

Both are documented rules over stored figures. These tests fix the rules, the wording of the reasons (real numbers) and the
refusal to judge on too little evidence.
"""

import uuid

import pytest

from app.competency import gaps, risk


def gap_input(**overrides) -> gaps.GapInput:
    base = dict(competency_id=uuid.uuid4(), code="sql.joins", name="SQL Joins", mastery=0.35, confidence=0.6, trend="stable", trend_delta=0.0,
                evidence_count=5, incorrect_count=1, retry_count=0, error_distribution={}, time_on_task_seconds=0, target_mastery=0.70)
    base.update(overrides)
    return gaps.GapInput(**base)


# ------------------------------------------------------------------ skill gaps
def test_mastery_below_target_with_enough_evidence_is_a_gap_with_the_figures_in_the_reason():
    a = gaps.assess(gap_input(mastery=0.35))
    assert a.is_gap and a.gap_size == pytest.approx(0.35)
    assert "35%" in a.reasons[0] and "70%" in a.reasons[0]


def test_mastery_at_or_above_target_is_not_a_gap():
    assert not gaps.assess(gap_input(mastery=0.70)).is_gap
    assert not gaps.assess(gap_input(mastery=0.95)).is_gap


def test_too_little_evidence_is_not_enough_to_call_a_gap_and_says_so():
    a = gaps.assess(gap_input(mastery=0.10, evidence_count=1))
    assert not a.is_gap and a.severity is None and a.points == 0
    assert "Not enough evidence" in a.note and "1 of 2" in a.note


def test_the_evidence_minimum_is_two():
    assert gaps.assess(gap_input(mastery=0.1, evidence_count=2)).is_gap


@pytest.mark.parametrize("mastery,points", [(0.25, 3), (0.45, 2), (0.60, 1)])
def test_the_size_of_the_shortfall_sets_the_base_points(mastery, points):
    assert gaps.assess(gap_input(mastery=mastery)).signals[0].points == points


def test_other_signals_explain_a_gap_and_add_points_with_real_figures():
    a = gaps.assess(gap_input(mastery=0.30, confidence=0.2, trend="declining", trend_delta=-0.18, incorrect_count=4,
                              error_distribution={"conceptual_misunderstanding": 3, "unknown": 1}, retry_count=3,
                              time_on_task_seconds=3000, expected_time_seconds=900))
    codes = [s.code for s in a.signals]
    assert codes == ["low_mastery", "low_confidence", "negative_trend", "repeated_errors", "high_retry_rate", "long_time_on_task"]
    text = " | ".join(a.reasons)
    assert "0.18" in text and "4 incorrect" in text and "conceptual misunderstanding (3)" in text and "3 of 5" in text and "50 minutes" in text
    assert a.severity == "critical" and a.points >= 7


def test_severity_is_points_not_completion():
    assert gaps.severity_for(7) == "critical" and gaps.severity_for(5) == "high" and gaps.severity_for(3) == "medium" and gaps.severity_for(1) == "low"


def test_signals_alone_do_not_make_a_gap():
    """A learner above target with a declining trend is not a skill gap: the other signals only explain one."""
    a = gaps.assess(gap_input(mastery=0.85, trend="declining", trend_delta=-0.2, incorrect_count=5))
    assert not a.is_gap and a.signals == [] and a.reasons == []


def test_an_unassessed_prerequisite_is_noted_and_a_low_one_blocks():
    unassessed = gaps.Prerequisite(uuid.uuid4(), "Relational Algebra", 0.6, None)
    low = gaps.Prerequisite(uuid.uuid4(), "SQL Basics", 0.6, 0.3)
    a = gaps.assess(gap_input(prerequisites=[unassessed, low]))
    assert [s.code for s in a.signals].count("prerequisite_blocked") == 1
    assert "SQL Basics" in " ".join(a.reasons) and "30%" in " ".join(a.reasons)
    assert "Relational Algebra" in a.note


def test_repeated_errors_name_the_most_frequent_type_only_when_it_repeats():
    once = gaps.assess(gap_input(incorrect_count=3, error_distribution={"careless_error": 1, "knowledge_gap": 1, "misreading": 1}))
    assert "most often" not in " ".join(once.reasons)
    twice = gaps.assess(gap_input(incorrect_count=3, error_distribution={"careless_error": 2, "misreading": 1}))
    assert "careless error (2)" in " ".join(twice.reasons)


def test_gap_output_is_plain_data():
    d = gaps.assess(gap_input()).as_dict()
    assert d["is_gap"] is True and isinstance(d["signals"][0], dict) and isinstance(d["competency_id"], str)


def test_cohort_summary_reports_counts_and_ignores_learners_with_too_little_evidence():
    cid = str(uuid.uuid4())
    rows = [{"competency_id": cid, "name": "SQL Joins", "user_id": i, "mastery": m, "trend": t, "evidence_count": n}
            for i, (m, t, n) in enumerate([(0.30, "declining", 4), (0.50, "stable", 3), (0.90, "improving", 6), (0.10, "stable", 1)])]
    [summary] = gaps.cohort_summary(rows, {cid: 0.7})
    assert summary["assessed_learners"] == 3 and summary["learners_below_target"] == 2      # the learner with one answer is not assessed
    assert summary["share_below_target"] == pytest.approx(2 / 3, abs=1e-3) and summary["learners_declining"] == 1
    assert summary["lowest_mastery"] == 0.30 and summary["evidence_count"] == 13


def test_cohort_summary_skips_a_competency_nobody_has_enough_evidence_for():
    rows = [{"competency_id": "c", "name": "X", "user_id": 1, "mastery": 0.1, "trend": "stable", "evidence_count": 1}]
    assert gaps.cohort_summary(rows, {}) == []


def test_cohort_summary_orders_the_worst_first():
    rows = []
    for cid, name, masteries in (("a", "Fine", (0.9, 0.8)), ("b", "Bad", (0.2, 0.3))):
        rows += [{"competency_id": cid, "name": name, "user_id": i, "mastery": m, "trend": "stable", "evidence_count": 3} for i, m in enumerate(masteries)]
    assert [s["name"] for s in gaps.cohort_summary(rows, {})] == ["Bad", "Fine"]


# ------------------------------------------------------------------ risk
def fact(**overrides) -> risk.CompetencyFact:
    base = dict(competency_id=str(uuid.uuid4()), name="SQL Joins", mastery=0.8, confidence=0.7, trend="stable", trend_delta=0.0, evidence_count=6,
                retry_count=0, time_on_task_seconds=600, expected_time_seconds=900, evidence_ids=("e1",), blocked_by=())
    base.update(overrides)
    return risk.CompetencyFact(**base)


def assess(*facts, failed=None, inactive=1.0, enrolled=30.0) -> risk.RiskAssessment:
    return risk.assess(risk.RiskInput(list(facts), failed or {}, inactive, enrolled))


def test_a_healthy_learner_has_no_factors_and_low_risk():
    a = assess(fact(), fact())
    assert a.level == "low" and a.points == 0 and a.factors == [] and a.score == 0.0 and a.actions == []


def test_no_evidence_and_no_activity_is_reported_as_unknown_not_as_risk():
    a = risk.assess(risk.RiskInput([], {}, None, 2.0))
    assert a.level == "low" and "cannot be assessed" in a.note


def test_persistent_low_mastery_needs_enough_evidence_and_confidence():
    assert assess(fact(mastery=0.3, evidence_count=2)).factors == []                 # too little evidence
    assert assess(fact(mastery=0.3, confidence=0.2)).factors == []                   # too little confidence
    a = assess(fact(mastery=0.3, name="SQL Joins"))
    assert [f.code for f in a.factors] == ["persistent_low_mastery"] and "SQL Joins (0.30)" in a.factors[0].description and a.factors[0].evidence_ids == ["e1"]


def test_two_low_competencies_weigh_more_than_one():
    one = assess(fact(mastery=0.3)).points
    two = assess(fact(mastery=0.3), fact(mastery=0.2)).points
    assert two > one


def test_a_declining_trend_cites_the_change():
    a = assess(fact(trend="declining", trend_delta=-0.22))
    assert a.factors[0].code == "negative_trend" and "-0.22" in a.factors[0].description


def test_repeated_failed_attempts_need_at_least_two():
    assert assess(fact(), failed={"Joins quiz": 1}).factors == []
    a = assess(fact(), failed={"Joins quiz": 3})
    assert a.factors[0].code == "repeated_failed_attempts" and "3 failed attempts" in a.factors[0].description and a.factors[0].points == 2


def test_high_retries_are_a_share_of_the_evidence():
    assert assess(fact(retry_count=1, evidence_count=6)).factors == []
    a = assess(fact(retry_count=3, evidence_count=6))
    assert a.factors[0].code == "high_retries" and "3 of 6" in a.factors[0].description


def test_long_time_on_task_compares_with_the_expected_time():
    assert assess(fact(time_on_task_seconds=1500, expected_time_seconds=900)).factors == []
    a = assess(fact(time_on_task_seconds=3600, expected_time_seconds=900))
    assert a.factors[0].code == "long_time_on_task" and "60 minutes" in a.factors[0].description


def test_no_expected_time_means_no_long_time_judgement():
    assert assess(fact(time_on_task_seconds=99999, expected_time_seconds=0)).factors == []


@pytest.mark.parametrize("days,points", [(3, 0), (7, 2), (13, 2), (14, 3), (40, 3)])
def test_inactivity_is_measured_in_days_since_the_last_real_event(days, points):
    assert assess(fact(), inactive=days).points == points


def test_never_active_counts_only_after_a_week_of_enrolment():
    assert risk.assess(risk.RiskInput([fact()], {}, None, 3.0)).factors == []
    a = risk.assess(risk.RiskInput([fact()], {}, None, 10.0))
    assert a.factors[0].code == "inactive_learning" and "10 days since enrolment" in a.factors[0].description


def test_prerequisite_gaps_name_the_prerequisite():
    a = assess(fact(name="Window Functions", blocked_by=["SQL Basics ≥ 60%"]))
    assert a.factors[0].code == "prerequisite_gaps" and "SQL Basics" in a.factors[0].description


def test_levels_come_from_points_and_the_score_from_the_same_total():
    assert [risk.level_for(p) for p in (0, 2, 3, 4, 5, 7, 8, 12)] == ["low", "low", "medium", "medium", "high", "high", "critical", "critical"]
    a = assess(fact(mastery=0.2), fact(mastery=0.3, trend="declining", trend_delta=-0.3), failed={"q": 4}, inactive=20)
    assert a.level == "critical" and a.score == min(1.0, a.points / 10)


def test_every_factor_has_an_action_and_details_are_plain_data():
    a = assess(fact(mastery=0.2, trend="declining", trend_delta=-0.3, retry_count=4), failed={"q": 2}, inactive=9)
    assert len(a.actions) == len(a.factors) and all(a.actions)
    assert all(set(d) == {"code", "description", "points", "value", "evidence_ids"} for d in a.details())
