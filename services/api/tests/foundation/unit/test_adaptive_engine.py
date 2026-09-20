"""
The adaptive decision function (app/adaptive/engine.py): one rule per situation, and an explanation made only of the facts.
"""

from datetime import datetime, timedelta

import pytest

from app.adaptive import engine as e

NOW = datetime(2026, 9, 20, 12, 0)


def cand(cid, title, kind="lesson", ctype="ARTICLE", comps=("c1",), difficulty=None, done=False, done_at=None, order=0):
    return e.Candidate(cid, title, ctype, kind, list(comps), "course", difficulty, done, done_at, order)


def ev(i, signal, error=None, difficulty=None, minutes=0):
    return e.Evidence(f"ev{i}", signal, error, difficulty, NOW - timedelta(minutes=minutes))


def situation(mastery=0.4, confidence=0.6, trend="stable", recent=(), candidates=None, prereqs=(), target=0.7, last_type=None, prereq_c=None, others=()):
    state = e.State("c1", "SQL Joins", mastery, confidence, trend, len(recent), target)
    default = [cand("l1", "Joins explained", order=1), cand("l2", "Joins video", ctype="VIDEO", order=2), cand("q1", "Joins quiz", "assessment", "QUIZ", difficulty=0.5, order=3)]
    return e.Situation(state, list(recent), list(prereqs), candidates if candidates is not None else default, prereq_c or {}, list(others), last_type)


def test_no_evidence_and_unstudied_material_starts_with_the_material():
    d = e.decide(situation(mastery=None))
    assert (d.action, d.rule, d.content.content_id) == ("CONTINUE", "no_evidence_learn", "l1")


def test_no_evidence_after_studying_is_an_assessment():
    d = e.decide(situation(mastery=None, candidates=[cand("l1", "L", done=True, done_at=NOW), cand("q1", "Q", "assessment", "QUIZ")]))
    assert (d.action, d.rule, d.content.content_id) == ("ASSESS", "no_evidence_assess", "q1")


def test_a_struggling_learner_is_sent_to_the_lesson_with_their_evidence_as_the_reason():
    d = e.decide(situation(0.38, recent=[ev(1, 0, "conceptual_misunderstanding", 0.5, 2), ev(2, 0, "conceptual_misunderstanding", 0.5, 4), ev(3, 1, None, 0.5, 6)]))
    assert (d.action, d.rule, d.content.content_id) == ("REMEDIATE", "struggling", "l1")
    why = e.explain(d)
    assert "2 of your last 3 answers were incorrect" in why["evidence"] and "2 answers with a conceptual misunderstanding error" in why["evidence"]
    assert why["mastery"] == 0.38 and set(why["evidence_ids"]) >= {"ev1", "ev2"}


def test_when_all_material_has_been_seen_it_is_revisited():
    seen = [cand("l1", "Joins explained", done=True, done_at=NOW - timedelta(days=2))]
    d = e.decide(situation(0.3, recent=[ev(1, 0, None, 0.5, 1)], candidates=seen))
    assert d.action == "REVISIT" and d.content.content_id == "l1"


def test_content_finished_after_the_last_answer_leads_to_a_new_assessment():
    done = [cand("l1", "Joins explained", done=True, done_at=NOW - timedelta(minutes=1)), cand("q1", "Quiz", "assessment", "QUIZ")]
    d = e.decide(situation(0.42, recent=[ev(1, 0, None, 0.5, 30)], candidates=done))
    assert (d.action, d.rule, d.content.content_id) == ("ASSESS", "reassess_after_content", "q1")
    assert "Joins explained" in d.reason


def test_the_same_typed_error_three_times_changes_the_modality():
    wrong = [ev(i, 0, "procedural_error", 0.5, i) for i in range(3)]
    items = [cand("l1", "Article", done=True, done_at=NOW - timedelta(days=1)), cand("l2", "Video", ctype="VIDEO", order=2)]
    d = e.decide(situation(0.45, recent=wrong, candidates=items, last_type="ARTICLE"))
    assert (d.action, d.rule, d.content.content_id) == ("CHANGE_MODALITY", "repeated_error_type", "l2")
    assert "article" in d.reason.lower() and "procedural error" in d.reason


def test_modality_is_not_changed_when_there_is_nothing_in_another_format():
    wrong = [ev(i, 0, "procedural_error", 0.5, i) for i in range(3)]
    d = e.decide(situation(0.45, recent=wrong, candidates=[cand("l1", "Article", order=1)], last_type="ARTICLE"))
    assert d.action != "CHANGE_MODALITY" and any("another format" in c for c in d.considered)


def test_two_wrong_answers_to_hard_questions_get_an_easier_step():
    hard = [ev(1, 0, None, 0.8, 1), ev(2, 0, None, 0.7, 3)]
    items = [cand("l1", "Advanced joins", difficulty=0.75, order=1), cand("l2", "Joins basics", difficulty=0.25, order=2)]
    d = e.decide(situation(0.3, recent=hard, candidates=items))
    assert (d.action, d.rule, d.content.content_id) == ("EASIER", "too_hard", "l2")


def test_an_unmet_prerequisite_is_remedied_first():
    pre = [e.Prerequisite("c0", "SQL Basics", 0.6, 0.3)]
    d = e.decide(situation(0.5, recent=[ev(1, 1, None, 0.5, 5)], prereqs=pre, prereq_c={"c0": [cand("p1", "SQL Basics lesson", comps=("c0",))]}))
    assert (d.action, d.rule, d.competency_id, d.content.content_id) == ("REMEDIATE", "prerequisite_gap", "c0", "p1")
    assert "SQL Basics" in e.explain(d)["evidence"][-1]


def test_an_unassessed_prerequisite_does_not_block():
    pre = [e.Prerequisite("c0", "SQL Basics", 0.6, None)]
    assert e.decide(situation(0.6, recent=[ev(1, 1, None, 0.5)], prereqs=pre)).rule != "prerequisite_gap"


def test_too_little_evidence_asks_for_more():
    d = e.decide(situation(0.6, confidence=0.2, recent=[ev(1, 1)]))
    assert (d.action, d.rule) == ("ASSESS", "low_confidence")


def test_a_falling_trend_is_revisited():
    seen = [cand("l1", "Joins explained", done=True, done_at=NOW - timedelta(days=5)), cand("q1", "Q", "assessment", "QUIZ")]
    d = e.decide(situation(0.62, trend="declining", recent=[ev(1, 1, None, 0.5, 1), ev(2, 0, None, 0.5, 2)], candidates=seen))
    assert (d.action, d.rule) == ("REVISIT", "declining")


def test_a_mastered_streak_skips_ahead():
    streak = [ev(i, 1, None, 0.6, i) for i in range(4)]
    d = e.decide(situation(0.95, confidence=0.8, recent=streak, others=[cand("n1", "Window functions", comps=("c2",))]))
    assert (d.action, d.rule, d.content.content_id) == ("SKIP", "mastered_streak", "n1")
    assert "4 correct answers in a row" in e.explain(d)["evidence"]


def test_above_target_with_high_accuracy_gets_a_harder_assessment():
    good = [ev(i, 1, None, 0.5, i) for i in range(4)]
    quizzes = [cand("q1", "Easy quiz", "assessment", "QUIZ", difficulty=0.4, done=True), cand("q2", "Hard quiz", "assessment", "QUIZ", difficulty=0.8)]
    d = e.decide(situation(0.82, confidence=0.6, recent=good, candidates=quizzes))
    assert (d.action, d.rule, d.content.content_id) == ("HARDER", "above_target", "q2")


def test_otherwise_it_continues_and_says_when_everything_is_done():
    d = e.decide(situation(0.65, recent=[ev(1, 1, None, 0.5, 1), ev(2, 0, None, 0.5, 2)]))
    assert (d.action, d.rule) == ("CONTINUE", "default") and d.content.content_id == "l1"
    finished = [cand("l1", "L", done=True, done_at=NOW - timedelta(days=1)), cand("q1", "Q", "assessment", "QUIZ", done=True)]
    d2 = e.decide(situation(0.65, recent=[ev(1, 1, None, 0.5, 1)], candidates=finished))
    assert d2.content is None and "completed everything" in d2.reason


def test_a_competency_with_no_material_is_reported_not_invented():
    d = e.decide(situation(0.3, recent=[ev(1, 0)], candidates=[]))
    assert d.content is None and d.note and "No material" in d.note


def test_the_explanation_contains_only_stored_facts():
    d = e.decide(situation(0.55, recent=[ev(1, 1, None, 0.5, 1)]))
    why = e.explain(d)
    assert why["headline"] == d.reason and why["rule"] == d.rule and why["mastery"] == 0.55
    assert all(isinstance(x, str) for x in why["evidence"])
    assert not any("incorrect" in x for x in why["evidence"])       # nothing was incorrect, so nothing says so


@pytest.mark.parametrize("mastery,signal,expected", [(0.2, 0, "REMEDIATE"), (0.65, 1, "CONTINUE")])
def test_decisions_are_deterministic(mastery, signal, expected):
    s = situation(mastery, recent=[ev(1, signal, None, 0.5, 1)])
    assert e.decide(s).action == e.decide(s).action == expected
