"""
Skill graph: prerequisite relationships between competencies.

An edge (competency, prerequisite) means "to learn `competency` you should first
have `prerequisite`". The graph must stay a DAG.

The first half of this module is pure graph algorithms over edge tuples (no
database), so it is unit testable and reusable by the adaptive and risk engines
in later phases. The second half is the tenant-scoped database service.

Terminology used consistently below:
    requires[c]   -> the set of DIRECT prerequisites of c
    dependents[p] -> the set of competencies that directly require p
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Competency, CompetencyPrerequisite

Edge = Tuple[UUID, UUID]  # (competency_id, prerequisite_id)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class SkillGraphError(Exception):
    """Base class. `code` is a stable machine-readable identifier for API clients."""
    code = "skill_graph_error"
    status_code = 400


class CompetencyNotFound(SkillGraphError):
    code = "competency_not_found"
    status_code = 404


class SelfPrerequisite(SkillGraphError):
    code = "self_prerequisite"
    status_code = 400


class DuplicatePrerequisite(SkillGraphError):
    code = "duplicate_prerequisite"
    status_code = 409


class PrerequisiteNotFound(SkillGraphError):
    code = "prerequisite_not_found"
    status_code = 404


class PrerequisiteCycle(SkillGraphError):
    """Adding the edge would create a cycle. `path` is the offending loop."""
    code = "prerequisite_cycle"
    status_code = 409

    def __init__(self, message: str, path: Sequence[UUID]):
        super().__init__(message)
        self.path = list(path)


# ---------------------------------------------------------------------------
# Pure graph algorithms
# ---------------------------------------------------------------------------
def build_requires(edges: Iterable[Edge]) -> Dict[UUID, Set[UUID]]:
    requires: Dict[UUID, Set[UUID]] = defaultdict(set)
    for competency_id, prerequisite_id in edges:
        requires[competency_id].add(prerequisite_id)
    return requires


def build_dependents(edges: Iterable[Edge]) -> Dict[UUID, Set[UUID]]:
    dependents: Dict[UUID, Set[UUID]] = defaultdict(set)
    for competency_id, prerequisite_id in edges:
        dependents[prerequisite_id].add(competency_id)
    return dependents


def find_cycle_path(
    edges: Iterable[Edge], competency_id: UUID, prerequisite_id: UUID
) -> Optional[List[UUID]]:
    """
    Would adding "competency requires prerequisite" create a cycle?

    It does exactly when `prerequisite` already (transitively) requires
    `competency`. Returns the loop as a list of ids starting and ending at
    `competency_id`, or None when the edge is safe.
    """
    if competency_id == prerequisite_id:
        return [competency_id, competency_id]

    requires = build_requires(edges)
    # BFS from the would-be prerequisite, walking "requires" edges, looking for `competency_id`.
    parent: Dict[UUID, Optional[UUID]] = {prerequisite_id: None}
    queue = deque([prerequisite_id])
    while queue:
        node = queue.popleft()
        for nxt in requires.get(node, ()):
            if nxt in parent:
                continue
            parent[nxt] = node
            if nxt == competency_id:
                # Walk the parents back to the start to recover the existing chain
                # prerequisite -> ... -> competency (each step is a "requires" edge).
                chain = [nxt]
                cursor: Optional[UUID] = node
                while cursor is not None:
                    chain.append(cursor)
                    cursor = parent[cursor]
                chain.reverse()
                # The new edge (competency -> prerequisite) closes the loop.
                return [competency_id] + chain
            queue.append(nxt)
    return None


def topological_levels(nodes: Iterable[UUID], edges: Iterable[Edge]) -> Dict[UUID, int]:
    """
    Depth of each competency in the graph. Level 0 has no prerequisites; a node's
    level is 1 + the maximum level of its prerequisites.

    Raises PrerequisiteCycle if the edge set is not a DAG (defensive: the write
    path prevents cycles, but data can be imported or edited out of band).
    """
    node_set = set(nodes)
    edge_list = [(c, p) for c, p in edges if c in node_set and p in node_set]
    requires = build_requires(edge_list)
    dependents = build_dependents(edge_list)

    remaining_prereqs = {n: len(requires.get(n, ())) for n in node_set}
    levels: Dict[UUID, int] = {}
    queue = deque(n for n, count in remaining_prereqs.items() if count == 0)
    for n in queue:
        levels[n] = 0

    processed = 0
    while queue:
        node = queue.popleft()
        processed += 1
        for dependent in dependents.get(node, ()):
            levels[dependent] = max(levels.get(dependent, 0), levels[node] + 1)
            remaining_prereqs[dependent] -= 1
            if remaining_prereqs[dependent] == 0:
                queue.append(dependent)

    if processed != len(node_set):
        stuck = [n for n, count in remaining_prereqs.items() if count > 0]
        raise PrerequisiteCycle("Skill graph contains a cycle", stuck)
    return levels


def transitive_prerequisites(edges: Iterable[Edge], competency_id: UUID) -> Set[UUID]:
    """Every competency that must come before `competency_id`, directly or indirectly."""
    requires = build_requires(edges)
    seen: Set[UUID] = set()
    stack = list(requires.get(competency_id, ()))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(requires.get(node, ()))
    return seen


@dataclass(frozen=True)
class UnmetPrerequisite:
    prerequisite_id: UUID
    required_mastery: float
    current_mastery: float


def unmet_prerequisites(
    requirements: Iterable[Tuple[UUID, float]],
    mastery_by_competency: Mapping[UUID, float],
) -> List[UnmetPrerequisite]:
    """
    Which direct prerequisites are not yet mastered enough?

    `requirements` is (prerequisite_id, min_mastery) pairs for ONE competency.
    A prerequisite with no recorded mastery counts as 0.0 — the learner has shown
    no evidence for it. Used by the adaptive and risk engines (later phases) to
    detect "prerequisite blockage".
    """
    unmet: List[UnmetPrerequisite] = []
    for prerequisite_id, required in requirements:
        current = mastery_by_competency.get(prerequisite_id, 0.0)
        if current < required:
            unmet.append(UnmetPrerequisite(prerequisite_id, required, current))
    return unmet


# ---------------------------------------------------------------------------
# Tenant-scoped database service
# ---------------------------------------------------------------------------
async def load_edges(db: AsyncSession, org_id: UUID) -> List[CompetencyPrerequisite]:
    result = await db.execute(
        select(CompetencyPrerequisite).where(CompetencyPrerequisite.org_id == org_id)
    )
    return list(result.scalars().all())


async def _require_competency(db: AsyncSession, org_id: UUID, competency_id: UUID) -> Competency:
    result = await db.execute(
        select(Competency).where(and_(Competency.id == competency_id, Competency.org_id == org_id))
    )
    competency = result.scalar_one_or_none()
    if competency is None:
        # Same error whether the id does not exist or belongs to another tenant.
        raise CompetencyNotFound(f"Competency {competency_id} not found")
    return competency


async def add_prerequisite(
    db: AsyncSession,
    org_id: UUID,
    competency_id: UUID,
    prerequisite_id: UUID,
    min_mastery: float = 0.6,
    rationale: Optional[str] = None,
    created_by_id: Optional[UUID] = None,
) -> CompetencyPrerequisite:
    if competency_id == prerequisite_id:
        raise SelfPrerequisite("A competency cannot be its own prerequisite")

    await _require_competency(db, org_id, competency_id)
    await _require_competency(db, org_id, prerequisite_id)

    existing_edges = await load_edges(db, org_id)
    if any(e.competency_id == competency_id and e.prerequisite_id == prerequisite_id for e in existing_edges):
        raise DuplicatePrerequisite("This prerequisite already exists")

    cycle = find_cycle_path(
        [(e.competency_id, e.prerequisite_id) for e in existing_edges], competency_id, prerequisite_id
    )
    if cycle:
        raise PrerequisiteCycle(
            "Adding this prerequisite would create a circular dependency", cycle
        )

    edge = CompetencyPrerequisite(
        competency_id=competency_id,
        prerequisite_id=prerequisite_id,
        org_id=org_id,
        min_mastery=min_mastery,
        rationale=rationale,
        created_by_id=created_by_id,
    )
    db.add(edge)
    await db.flush()
    return edge


async def remove_prerequisite(
    db: AsyncSession, org_id: UUID, competency_id: UUID, prerequisite_id: UUID
) -> None:
    result = await db.execute(
        delete(CompetencyPrerequisite).where(
            and_(
                CompetencyPrerequisite.org_id == org_id,
                CompetencyPrerequisite.competency_id == competency_id,
                CompetencyPrerequisite.prerequisite_id == prerequisite_id,
            )
        )
    )
    if result.rowcount == 0:
        raise PrerequisiteNotFound("Prerequisite relationship not found")


async def build_graph(db: AsyncSession, org_id: UUID) -> dict:
    """The whole tenant skill graph: nodes with depth, plus edges. Suitable for rendering."""
    competencies = (
        await db.execute(select(Competency).where(Competency.org_id == org_id).order_by(Competency.name))
    ).scalars().all()
    edge_rows = await load_edges(db, org_id)
    edges = [(e.competency_id, e.prerequisite_id) for e in edge_rows]

    node_ids = [c.id for c in competencies]
    levels = topological_levels(node_ids, edges)
    requires = build_requires(edges)
    dependents = build_dependents(edges)

    nodes = [
        {
            "id": c.id,
            "code": c.code,
            "name": c.name,
            "domain": c.domain,
            "difficulty": c.difficulty,
            "taxonomy_level": c.taxonomy_level,
            "level": levels.get(c.id, 0),
            "prerequisite_ids": sorted(requires.get(c.id, ()), key=str),
            "dependent_ids": sorted(dependents.get(c.id, ()), key=str),
        }
        for c in competencies
    ]
    return {
        "nodes": nodes,
        "edges": [
            {
                "competency_id": e.competency_id,
                "prerequisite_id": e.prerequisite_id,
                "min_mastery": e.min_mastery,
                "rationale": e.rationale,
            }
            for e in edge_rows
        ],
        "domains": sorted({c.domain for c in competencies if c.domain}),
        "max_level": max(levels.values(), default=0),
    }
