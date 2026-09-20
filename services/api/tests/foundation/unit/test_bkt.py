"""
The deterministic mastery update (app/competency/bkt.py): the only place a mastery figure is calculated.

These tests state the properties the rest of the system relies on: the figure stays a probability, the same evidence always gives
the same figure, evidence pushes in the right direction, weaker evidence pushes less, and a stored chain can be recomputed.
"""

import itertools

import pytest

from app.competency import bkt
from app.competency.bkt import Evidence, MasteryParams, update

P = MasteryParams()


def run(*evidence, params=P):
    return bkt.fold(list(evidence), params)


# ------------------------------------------------------------------ bounds and determinism
@pytest.mark.parametrize("signal,confidence,difficulty,attempt,floor", list(itertools.product(
    (0.0, 0.3, 1.0), (0.0, 0.5, 1.0), (None, 0.0, 1.0), (None, 1, 5), (None, 0.25))))
def test_mastery_and_confidence_stay_probabilities(signal, confidence, difficulty, attempt, floor):
    result = update(None, 0.0, Evidence(signal, confidence, difficulty, attempt, floor), P)
    assert 0.0 < result.new_mastery < 1.0
    assert 0.0 <= result.new_confidence < 1.0
    assert result.weight >= 0.0


def test_long_runs_never_leave_the_open_interval():
    for signal in (0.0, 1.0):
        results = run(*[Evidence(signal)] * 200)
        assert all(0.0 < r.new_mastery < 1.0 for r in results)


def test_same_inputs_give_the_same_figure():
    evidence = [Evidence(1.0, difficulty=0.4), Evidence(0.0, 0.8, attempt_number=2), Evidence(0.6, 0.9)]
    assert run(*evidence) == run(*evidence)


def test_first_evidence_starts_from_the_prior_and_says_so():
    result = update(None, 0.0, Evidence(1.0), P)
    assert result.previous_mastery is None and result.previous_confidence is None


# ------------------------------------------------------------------ direction
def test_correct_answers_raise_mastery_and_wrong_answers_lower_it():
    up = update(0.5, 2.0, Evidence(1.0), P)
    down = update(0.5, 2.0, Evidence(0.0), P)
    assert up.new_mastery > 0.5 > down.new_mastery


def test_mastery_is_monotonic_in_the_signal():
    values = [update(0.5, 2.0, Evidence(s / 10), P).new_mastery for s in range(11)]
    assert values == sorted(values) and values[0] < values[-1]


def test_a_partial_signal_lands_between_wrong_and_right():
    wrong, partial, right = (update(0.5, 2.0, Evidence(s), P).new_mastery for s in (0.0, 0.5, 1.0))
    assert wrong < partial < right


def test_a_correct_answer_to_a_harder_question_counts_for_more():
    easy = update(0.4, 1.0, Evidence(1.0, difficulty=0.2), P).new_mastery
    hard = update(0.4, 1.0, Evidence(1.0, difficulty=0.8), P).new_mastery
    assert hard > easy


def test_a_wrong_answer_to_an_easier_question_costs_more():
    easy = update(0.6, 1.0, Evidence(0.0, difficulty=0.2), P).new_mastery
    hard = update(0.6, 1.0, Evidence(0.0, difficulty=0.8), P).new_mastery
    assert easy < hard


def test_guessing_a_two_option_question_proves_less_than_a_four_option_one():
    coin_flip = update(0.3, 1.0, Evidence(1.0, guess_floor=0.5), P).new_mastery
    four_way = update(0.3, 1.0, Evidence(1.0, guess_floor=0.25), P).new_mastery
    assert four_way > coin_flip


def test_repeated_correct_answers_climb_and_repeated_wrong_ones_stay_low():
    climbing = [r.new_mastery for r in run(*[Evidence(1.0)] * 6)]
    assert climbing == sorted(climbing) and climbing[-1] > 0.9
    failing = [r.new_mastery for r in run(*[Evidence(0.0)] * 6)]
    assert failing[-1] < 0.3          # never rises to "known" on wrong answers alone


# ------------------------------------------------------------------ weight: source confidence and retries
def test_a_second_attempt_moves_mastery_less_than_a_first_attempt():
    first = update(0.4, 1.0, Evidence(1.0, attempt_number=1), P).new_mastery
    second = update(0.4, 1.0, Evidence(1.0, attempt_number=2), P).new_mastery
    third = update(0.4, 1.0, Evidence(1.0, attempt_number=3), P).new_mastery
    assert first > second > third > 0.4


def test_weight_is_source_confidence_times_the_retry_discount():
    result = update(0.4, 1.0, Evidence(1.0, confidence=0.8, attempt_number=3), P)
    assert result.weight == pytest.approx(0.8 * P.retry_weight ** 2, abs=1e-6)


def test_less_trusted_evidence_moves_mastery_less():
    sure = update(0.4, 1.0, Evidence(1.0, confidence=1.0), P).new_mastery
    unsure = update(0.4, 1.0, Evidence(1.0, confidence=0.4), P).new_mastery
    assert sure > unsure > 0.4


def test_zero_weight_evidence_changes_nothing():
    result = update(0.4, 1.0, Evidence(0.0, confidence=0.0), P)
    assert result.new_mastery == pytest.approx(0.4, abs=1e-6)
    assert result.effective_evidence == 1.0        # no weight, no added evidence


def test_wrong_answers_never_raise_mastery_however_little_they_weigh():
    """A run of wrong, heavily discounted retries used to climb because the learning step ignored the weight."""
    for start in (0.2, 0.5):
        mastery, effective = start, 3.0
        for attempt in range(1, 12):
            result = update(mastery, effective, Evidence(0.0, attempt_number=attempt), P)
            assert result.new_mastery <= mastery + P.learn * result.weight + 1e-9
            mastery, effective = result.new_mastery, result.effective_evidence
        assert mastery < start + 0.15


# ------------------------------------------------------------------ confidence
def test_confidence_is_evidence_weight_over_weight_plus_k():
    assert bkt.confidence_of(3.0, P) == pytest.approx(0.5)
    assert bkt.confidence_of(0.0, P) == 0.0
    assert bkt.confidence_of(9.0, P) == pytest.approx(0.75)


def test_confidence_grows_with_evidence_whatever_the_answers_were():
    results = run(*[Evidence(0.0)] * 5)
    confidences = [r.new_confidence for r in results]
    assert confidences == sorted(confidences)


def test_evidence_weight_accumulates_by_weight_not_by_count():
    results = run(Evidence(1.0), Evidence(1.0, attempt_number=2))
    assert results[-1].effective_evidence == pytest.approx(1.0 + P.retry_weight)


# ------------------------------------------------------------------ chains
def test_fold_is_the_step_by_step_chain():
    evidence = [Evidence(1.0), Evidence(0.0, difficulty=0.7), Evidence(0.8, 0.9, attempt_number=2)]
    folded = bkt.fold(evidence, P)
    mastery, effective = None, 0.0
    for item, expected in zip(evidence, folded):
        step = update(mastery, effective, item, P)
        assert step == expected
        mastery, effective = step.new_mastery, step.effective_evidence


def test_each_step_starts_where_the_previous_one_ended():
    steps = run(Evidence(1.0), Evidence(0.0), Evidence(1.0))
    for before, after in zip(steps, steps[1:]):
        assert after.previous_mastery == pytest.approx(before.new_mastery)


def test_parameters_are_returned_with_the_result_so_it_can_be_redone():
    custom = MasteryParams(prior=0.3, learn=0.05)
    result = update(None, 0.0, Evidence(1.0), custom)
    assert result.params["prior"] == 0.3 and result.params["learn"] == 0.05
    redone = update(None, 0.0, Evidence(1.0), MasteryParams(**result.params))
    assert redone == result


def test_a_different_prior_changes_the_start():
    low = update(None, 0.0, Evidence(1.0), MasteryParams(prior=0.1)).new_mastery
    high = update(None, 0.0, Evidence(1.0), MasteryParams(prior=0.5)).new_mastery
    assert low < high


# ------------------------------------------------------------------ trend
def test_trend_needs_enough_history():
    assert bkt.trend_of([0.2, 0.9]) == ("insufficient_data", None)
    assert bkt.trend_of([]) == ("insufficient_data", None)


def test_trend_reads_the_history_not_the_level():
    assert bkt.trend_of([0.2, 0.3, 0.5])[0] == "improving"
    assert bkt.trend_of([0.9, 0.8, 0.6])[0] == "declining"
    assert bkt.trend_of([0.5, 0.51, 0.52])[0] == "stable"
    # a high level is not "improving" and a low level is not "declining": the earlier code decided this from the level
    assert bkt.trend_of([0.95, 0.95, 0.95])[0] == "stable"
    assert bkt.trend_of([0.10, 0.10, 0.10])[0] == "stable"


def test_trend_compares_with_the_start_of_the_window():
    values = [0.9, 0.2, 0.2, 0.2, 0.2, 0.2, 0.25]          # the 0.9 is outside the window of 5 updates back
    label, delta = bkt.trend_of(values)
    assert label == "stable" and delta == pytest.approx(0.05, abs=1e-6)


def test_trend_delta_is_reported():
    label, delta = bkt.trend_of([0.3, 0.4, 0.6])
    assert label == "improving" and delta == pytest.approx(0.3)


# ------------------------------------------------------------------ status and accuracy
@pytest.mark.parametrize("mastery,expected", [(0.0, "novice"), (0.29, "novice"), (0.30, "developing"), (0.59, "developing"),
                                              (0.60, "competent"), (0.79, "competent"), (0.80, "proficient"), (0.90, "expert")])
def test_status_bands(mastery, expected):
    assert bkt.status_of(mastery) == expected


def test_recent_accuracy_is_a_weighted_mean_or_none():
    assert bkt.recent_accuracy([]) is None
    assert bkt.recent_accuracy([(1.0, 1.0), (0.0, 1.0)]) == pytest.approx(0.5)
    assert bkt.recent_accuracy([(1.0, 3.0), (0.0, 1.0)]) == pytest.approx(0.75)
    assert bkt.recent_accuracy([(1.0, 0.0)]) is None
    assert bkt.recent_accuracy([(1.0, 1.0)] * 3 + [(0.0, 1.0)] * 20, window=3) == pytest.approx(1.0)
