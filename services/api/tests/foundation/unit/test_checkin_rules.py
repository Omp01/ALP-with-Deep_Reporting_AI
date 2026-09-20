"""Check-in rules with no database: self-report scoring, item validation, passage selection, quiz scoring and the observations."""

import random
import uuid

import pytest

from app.checkin import psychometric as P
from app.checkin import quiz as Q
from app.checkin import report as R


def items(construct="self_efficacy", reverse_last=True):
    return [{"id": f"{construct}_{i}", "construct": construct, "text": "x" * 20, "reverse": reverse_last and i == 3} for i in (1, 2, 3)]


# ---------------------------------------------------------------- self-report scoring
def test_a_negatively_worded_statement_is_flipped():
    scored = P.score_construct(items(), {"self_efficacy_1": 5, "self_efficacy_2": 5, "self_efficacy_3": 1})
    assert scored["score"] == 100.0 and scored["band"] == "high"       # agreeing with the reverse statement would lower it, disagreeing raises it


@pytest.mark.parametrize("ratings,expected", [((1, 1, 5), 0.0), ((3, 3, 3), 50.0), ((5, 5, 1), 100.0), ((4, 4, 2), 75.0)])
def test_scores_run_from_0_to_100(ratings, expected):
    assert P.score_construct(items(), dict(zip(("self_efficacy_1", "self_efficacy_2", "self_efficacy_3"), ratings)))["score"] == expected


@pytest.mark.parametrize("score,band", [(0, "low"), (39.9, "low"), (40, "moderate"), (70, "moderate"), (70.1, "high"), (100, "high")])
def test_band_edges(score, band):
    assert P.band(score) == band


def test_too_few_answers_are_not_scored_and_bad_ratings_are_ignored():
    assert P.score_construct(items(), {"self_efficacy_1": 4}) is None
    assert P.score_construct(items(), {"self_efficacy_1": 9, "self_efficacy_2": True, "self_efficacy_3": "4"}) is None
    assert P.score_construct(items(), {"self_efficacy_1": 4, "self_efficacy_2": 4})["answered"] == 2


def test_the_change_since_the_previous_check_in_is_only_meaningful_past_the_threshold():
    all_items = [i for c in P.CONSTRUCTS for i in items(c.id, reverse_last=False)]
    answers = {i["id"]: 4 for i in all_items}                                 # 75 everywhere
    previous = {c.id: {"score": 70.0} for c in P.CONSTRUCTS}
    small = P.score_all(all_items, answers, previous, change_threshold=10)
    assert small["motivation"]["change"] == 5.0 and small["motivation"]["change_is_meaningful"] is False
    previous = {c.id: {"score": 50.0} for c in P.CONSTRUCTS}
    assert P.score_all(all_items, answers, previous, 10)["motivation"]["change_is_meaningful"] is True
    assert P.score_all(all_items, answers, None, 10)["motivation"]["change"] is None


# ------------------------------------------------------------------ item validation
def out(dimension, text, reverse=False):
    return P.ItemOut(dimension=dimension, text=text, reverse=reverse)


def statements(n=3):
    return [out(c.id, f"Statement {i} about {c.id.replace('_', ' ')} in this subject area.") for c in P.CONSTRUCTS for i in range(n)]


def test_well_formed_statements_are_kept_up_to_the_limit():
    kept, problems = P.validate_items(statements(5), per_construct=3)
    assert len(kept) == 12 and problems == [] and P.complete_enough(kept)
    assert kept[0]["id"] == "self_efficacy_1"


def test_unknown_constructs_questions_and_duplicates_are_dropped():
    raw = statements(3) + [out("astrology", "The stars are aligned for my learning today, I believe."),
                           out("motivation", "Do I feel motivated to learn this subject at all?"),
                           out("motivation", "Statement 0 about motivation in this subject area.")]
    kept, problems = P.validate_items(raw, per_construct=3)
    assert len(kept) == 12
    assert any("astrology" in p for p in problems) and any("not a usable statement" in p for p in problems)


def test_a_construct_with_one_statement_makes_the_set_unusable():
    raw = [s for s in statements(3) if not (s.dimension == "motivation" and not s.text.startswith("Statement 0"))]
    kept, problems = P.validate_items(raw, per_construct=3)
    assert not P.complete_enough(kept) and any("Motivation" in p for p in problems)


def test_dimension_names_are_normalised():
    assert out("Self Efficacy", "I feel able to do this kind of work well.").dimension == "self_efficacy"
    assert out("self-efficacy", "I feel able to do this kind of work well.", "true").reverse is True


# ------------------------------------------------------------- passages and fresh questions
def test_split_text_merges_short_paragraphs_and_cuts_long_ones():
    pieces = Q.split_text("Short one.\n\nShort two.\n\n" + " ".join(["A sentence that keeps going."] * 60), target=200)
    assert pieces[0].startswith("Short one. Short two.") and len(pieces) > 3 and all(len(p) <= 260 for p in pieces)
    assert Q.split_text("") == [] and Q.split_text("  \n\n ") == []


def test_unused_passages_are_chosen_before_used_ones():
    passages = [Q.Passage(f"k{i}", uuid.uuid4(), "t", "text " * 20) for i in range(8)]
    chosen = Q.sample_passages(passages, used_before={"k0", "k1", "k2", "k3", "k4"}, k=3, rng=random.Random(1))
    assert {p.key for p in chosen} == {"k5", "k6", "k7"}
    more = Q.sample_passages(passages, used_before={f"k{i}" for i in range(8)}, k=3, rng=random.Random(1))
    assert len(more) == 3                                                    # when everything was used, it still returns some


def test_different_seeds_give_different_selections():
    passages = [Q.Passage(f"k{i}", uuid.uuid4(), "t", "text " * 20) for i in range(20)]
    picks = {tuple(p.key for p in Q.sample_passages(passages, set(), 5, random.Random(seed))) for seed in range(6)}
    assert len(picks) > 1


# ------------------------------------------------------------------------ quiz scoring
def question(qid, content="Lesson A", competency="Indexes"):
    return {"id": qid, "text": f"Question {qid}?", "explanation": "because", "source_quote": "quote", "content_item_id": content, "content_title": content,
            "competency_name": competency, "options": [{"id": "a", "text": "right", "is_correct": True}, {"id": "b", "text": "wrong", "is_correct": False}]}


def test_quiz_scoring_groups_by_lesson_and_competency_and_names_unanswered():
    qs = [question("q1"), question("q2"), question("q3", content="Lesson B", competency="Locks")]
    scored = R.score_quiz(qs, {"q1": "a", "q2": "b"})
    assert (scored["correct"], scored["total"], scored["percent"], scored["unanswered"]) == (1, 3, 33.3, 1)
    assert [r["name"] for r in scored["by_content"]] == ["Lesson B", "Lesson A"]           # weakest first
    assert next(r for r in scored["by_content"] if r["name"] == "Lesson A") == {"name": "Lesson A", "correct": 1, "total": 2, "content_item_id": "Lesson A"}
    assert scored["review"][1]["your_answer"] == "wrong" and scored["review"][2]["your_answer"] is None


# ------------------------------------------------------------------------- observations
def self_report(**bands):
    out = {}
    for c in P.CONSTRUCTS:
        b = bands.get(c.id)
        out[c.id] = {"label": c.label, "scored": b is not None, "band": b, "score": {"low": 20.0, "moderate": 55.0, "high": 90.0}.get(b), "change": None,
                     "previous": None, "change_is_meaningful": False}
    return out


def quiz_of(correct, total=5):
    return {"correct": correct, "total": total, "percent": round(100 * correct / total, 1), "by_content": [{"name": "Lesson A", "correct": correct, "total": total}]}


def texts(obs):
    return " ".join(o["text"] for o in obs)


def test_strong_answers_with_low_confidence_are_described_without_a_cause():
    obs = R.observations(quiz_of(5), self_report(self_efficacy="low"), None)
    assert "more than you reported" in texts(obs) and "cannot say why" in texts(obs)


def test_high_confidence_with_weak_answers_points_to_the_passages():
    assert "high but answered 1 of 5" in texts(R.observations(quiz_of(1), self_report(self_efficacy="high"), None))


def test_tension_with_a_weak_score_says_no_link_is_established():
    text = texts(R.observations(quiz_of(1), self_report(learning_anxiety="high"), None))
    assert "does not establish a link" in text and "caused" not in text


def test_the_trend_uses_the_previous_quiz_percent_and_warns_that_questions_differ():
    text = texts(R.observations(quiz_of(4), {}, 40.0))
    assert "up from 40% at your previous check-in to 80%" in text and "differ each time" in text


def test_no_observation_when_there_is_nothing_to_say():
    assert R.observations(quiz_of(5), self_report(self_efficacy="high"), None) == []


def test_observations_never_use_causal_wording():
    from app.reporting.validator import CAUSAL_PATTERNS, NEGATION
    import re
    for correct in (0, 1, 3, 5):
        for band in ("low", "moderate", "high"):
            for text in [o["text"] for o in R.observations(quiz_of(correct), self_report(self_efficacy=band, learning_anxiety=band, self_regulation=band), 50.0)]:
                scan = NEGATION.sub("", text)
                assert not any(re.search(p, scan, re.I) for p in CAUSAL_PATTERNS), text
