"""Pure tests for the skill-graph algorithms (no database)."""

import uuid

import pytest

from app.services.skill_graph import (
    PrerequisiteCycle,
    find_cycle_path,
    topological_levels,
    transitive_prerequisites,
    unmet_prerequisites,
)

pytestmark = pytest.mark.unit


def ids(n):
    return [uuid.uuid4() for _ in range(n)]


def test_linear_chain_levels():
    # streaming -> pyspark -> processing -> structures -> basics   (each "requires" the next)
    basics, structures, processing, pyspark, streaming = ids(5)
    edges = [(structures, basics), (processing, structures), (pyspark, processing), (streaming, pyspark)]
    levels = topological_levels([basics, structures, processing, pyspark, streaming], edges)
    assert [levels[n] for n in (basics, structures, processing, pyspark, streaming)] == [0, 1, 2, 3, 4]


def test_level_is_longest_path_not_shortest():
    a, b, c = ids(3)
    # c requires b and a; b requires a.  c is level 2 (via b), not 1 (via a directly).
    levels = topological_levels([a, b, c], [(b, a), (c, b), (c, a)])
    assert levels == {a: 0, b: 1, c: 2}


def test_isolated_competencies_are_level_zero():
    a, b = ids(2)
    assert topological_levels([a, b], []) == {a: 0, b: 0}


def test_topological_levels_detects_existing_cycle():
    a, b, c = ids(3)
    with pytest.raises(PrerequisiteCycle):
        topological_levels([a, b, c], [(a, b), (b, c), (c, a)])


def test_edges_referencing_unknown_nodes_are_ignored():
    a, b, stranger = ids(3)
    assert topological_levels([a, b], [(b, a), (stranger, a)]) == {a: 0, b: 1}


def test_self_edge_is_a_cycle():
    a = uuid.uuid4()
    assert find_cycle_path([], a, a) == [a, a]


def test_safe_edge_returns_none():
    a, b, c = ids(3)
    assert find_cycle_path([(b, a)], c, b) is None
    assert find_cycle_path([], a, b) is None


def test_direct_cycle_is_detected():
    a, b = ids(2)
    # b requires a already; making a require b closes a 2-loop.
    path = find_cycle_path([(b, a)], a, b)
    assert path == [a, b, a]


def test_indirect_cycle_is_detected_with_full_path():
    a, b, c = ids(3)
    # c requires b, b requires a.  Making a require c closes a -> c -> b -> a.
    path = find_cycle_path([(c, b), (b, a)], a, c)
    assert path == [a, c, b, a]
    assert path[0] == path[-1]


def test_diamond_is_not_a_cycle():
    top, left, right, bottom = ids(4)
    edges = [(left, top), (right, top), (bottom, left)]
    assert find_cycle_path(edges, bottom, right) is None  # bottom also requiring right is fine


def test_transitive_prerequisites():
    a, b, c, d = ids(4)
    edges = [(b, a), (c, b), (d, c), (d, a)]
    assert transitive_prerequisites(edges, d) == {a, b, c}
    assert transitive_prerequisites(edges, a) == set()
    assert transitive_prerequisites(edges, b) == {a}


def test_unmet_prerequisites_uses_threshold_and_missing_counts_as_zero():
    a, b, c = ids(3)
    unmet = unmet_prerequisites(
        requirements=[(a, 0.6), (b, 0.6), (c, 0.5)],
        mastery_by_competency={a: 0.75, b: 0.42},  # c has no evidence at all
    )
    assert {u.prerequisite_id for u in unmet} == {b, c}
    by_id = {u.prerequisite_id: u for u in unmet}
    assert by_id[b].current_mastery == 0.42 and by_id[b].required_mastery == 0.6
    assert by_id[c].current_mastery == 0.0


def test_prerequisite_exactly_at_threshold_is_met():
    a = uuid.uuid4()
    assert unmet_prerequisites([(a, 0.6)], {a: 0.6}) == []
