"""
The adaptive decision function (spec section 21). Pure: no database, no clock, no model.

Given what is stored about one learner and one competency, it returns one action, the content to do, the rule that fired,
and the facts behind it. The facts are the only source of the "Why am I seeing this?" text, so an explanation can never say
something the data does not.

Actions: CONTINUE, REMEDIATE, EASIER, HARDER, CHANGE_MODALITY, REVISIT, SKIP, ASSESS.

Rules are tried in this order and the first that applies wins (each has an id that is stored with the decision):

  no_evidence_learn      nothing assessed yet and there is unstudied material  -> CONTINUE with it
  no_evidence_assess     nothing assessed yet                                  -> ASSESS
  prerequisite_gap       a prerequisite is below the mastery it must reach     -> REMEDIATE that prerequisite
  repeated_error_type    the same typed error 3 times in the last 6 wrong      -> CHANGE_MODALITY
  too_hard               the last 2 wrong answers were hard questions          -> EASIER
  struggling             mastery below 0.5 and the latest answer was wrong     -> REMEDIATE (REVISIT if all material was seen)
  reassess_after_content content was completed since the last answer, below target -> ASSESS
  low_confidence         too little evidence to trust the estimate             -> ASSESS
  declining              mastery falling                                       -> REVISIT
  mastered_streak        mastery >= 0.90 with a streak of correct answers      -> SKIP ahead
  above_target           at or above target with high recent accuracy          -> HARDER
  default                                                                       -> CONTINUE

Thresholds are named constants below, documented in docs/ADAPTIVE_ENGINE.md.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

STRUGGLE_BELOW = 0.50
LOW_CONFIDENCE = 0.40
HARD_QUESTION = 0.65
CORRECT_AT = 0.70
REPEAT_ERRORS = 3
ERROR_WINDOW = 6
SKIP_MASTERY = 0.90
SKIP_CONFIDENCE = 0.60
SKIP_STREAK = 3
HARDER_ACCURACY = 0.80
DEFAULT_TARGET = 0.70

CONTINUE, REMEDIATE, EASIER, HARDER, CHANGE_MODALITY, REVISIT, SKIP, ASSESS = (
    "CONTINUE", "REMEDIATE", "EASIER", "HARDER", "CHANGE_MODALITY", "REVISIT", "SKIP", "ASSESS")
ACTIONS = (CONTINUE, REMEDIATE, EASIER, HARDER, CHANGE_MODALITY, REVISIT, SKIP, ASSESS)


@dataclass
class Candidate:
    content_id: str
    title: str
    content_type: str                       # VIDEO, ARTICLE, QUIZ, ASSIGNMENT, ...
    kind: str                               # lesson | assessment | assignment
    competency_ids: Sequence[str]
    course_id: Optional[str] = None
    difficulty: Optional[float] = None      # None: unknown (never assumed)
    completed: bool = False
    completed_at: Optional[datetime] = None
    order: int = 0


@dataclass
class Evidence:
    id: str
    signal: float
    error_type: Optional[str]
    difficulty: Optional[float]
    occurred_at: datetime


@dataclass
class Prerequisite:
    competency_id: str
    name: str
    required: float
    mastery: Optional[float]


@dataclass
class State:
    competency_id: str
    name: str
    mastery: Optional[float]                # None: no evidence
    confidence: float = 0.0
    trend: str = "insufficient_data"
    evidence_count: int = 0
    target: float = DEFAULT_TARGET


@dataclass
class Situation:
    state: State
    recent: Sequence[Evidence]              # newest first
    prerequisites: Sequence[Prerequisite]
    candidates: Sequence[Candidate]         # content that could be shown, any competency in scope
    prerequisite_candidates: Dict[str, Sequence[Candidate]] = field(default_factory=dict)   # by prerequisite competency id
    next_competency_candidates: Sequence[Candidate] = field(default_factory=list)          # material for other competencies, in course order
    last_consumed_type: Optional[str] = None      # content type of the latest lesson the learner finished for this competency


@dataclass
class Fact:
    label: str
    value: Any
    evidence_ids: Sequence[str] = field(default_factory=tuple)


@dataclass
class Decision:
    action: str
    rule: str
    competency_id: str
    competency_name: str
    content: Optional[Candidate]
    reason: str
    facts: List[Fact]
    considered: List[str] = field(default_factory=list)      # what else was possible and why it was not chosen
    note: Optional[str] = None                               # e.g. "no material is mapped to this competency"


def _wrong(e: Evidence) -> bool:
    return e.signal < STRUGGLE_BELOW


def _streak(recent: Sequence[Evidence]) -> int:
    n = 0
    for e in recent:
        if e.signal >= CORRECT_AT:
            n += 1
        else:
            break
    return n


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _lessons(items: Sequence[Candidate]) -> List[Candidate]:
    return [c for c in items if c.kind == "lesson"]


def _assessments(items: Sequence[Candidate]) -> List[Candidate]:
    return [c for c in items if c.kind == "assessment"]


def _first_open(items: Sequence[Candidate]) -> Optional[Candidate]:
    return next(iter(sorted((c for c in items if not c.completed), key=lambda c: c.order)), None)


def _latest_done(items: Sequence[Candidate]) -> Optional[Candidate]:
    done = [c for c in items if c.completed]
    return max(done, key=lambda c: (c.completed_at or datetime.min, c.order), default=None)


def _mastery_facts(s: Situation) -> List[Fact]:
    st = s.state
    facts = []
    if st.mastery is not None:
        facts.append(Fact("mastery", round(st.mastery, 4)))
        facts.append(Fact("confidence", round(st.confidence, 4)))
        facts.append(Fact("target", st.target))
        facts.append(Fact("trend", st.trend))
        facts.append(Fact("evidence_count", st.evidence_count))
    return facts


def _recent_facts(s: Situation) -> List[Fact]:
    facts: List[Fact] = []
    recent = list(s.recent)[:ERROR_WINDOW]
    wrong = [e for e in recent if _wrong(e)]
    if recent:
        facts.append(Fact("recent_answers", len(recent), [e.id for e in recent]))
        facts.append(Fact("recent_incorrect", len(wrong), [e.id for e in wrong]))
        typed = {}
        for e in wrong:
            if e.error_type and e.error_type != "unknown":
                typed[e.error_type] = typed.get(e.error_type, 0) + 1
        for kind, n in sorted(typed.items(), key=lambda kv: -kv[1]):
            facts.append(Fact(f"error:{kind}", n, [e.id for e in wrong if e.error_type == kind]))
        facts.append(Fact("latest_answer_at", recent[0].occurred_at.isoformat(), [recent[0].id]))
    return facts


def decide(s: Situation) -> Decision:
    st, recent = s.state, list(s.recent)
    base = _mastery_facts(s) + _recent_facts(s)
    lessons, quizzes = _lessons(s.candidates), _assessments(s.candidates)

    def out(action: str, rule: str, content: Optional[Candidate], reason: str, extra: Sequence[Fact] = (), considered: Sequence[str] = (), note: Optional[str] = None,
            competency_id: Optional[str] = None, competency_name: Optional[str] = None) -> Decision:
        return Decision(action, rule, competency_id or st.competency_id, competency_name or st.name, content, reason, list(base) + list(extra),
                        list(considered), note if content is not None or note else "No material is mapped to this competency yet.")

    # ---- nothing assessed yet
    if st.mastery is None:
        unread = _first_open(lessons)
        if unread is not None and not any(c.completed for c in lessons):
            return out(CONTINUE, "no_evidence_learn", unread,
                       f"You have not been assessed on {st.name} yet, and there is material to work through first.",
                       [Fact("lessons_available", len(lessons))])
        quiz = _first_open(quizzes) or (quizzes[0] if quizzes else None)
        return out(ASSESS, "no_evidence_assess", quiz,
                   f"There is no evidence about {st.name} yet, so a short assessment will show where you stand.")

    mastery, target = st.mastery, st.target
    considered: List[str] = []

    # ---- prerequisite gap
    gaps = [p for p in s.prerequisites if p.mastery is not None and p.mastery < p.required]
    if gaps and mastery < target:
        gap = min(gaps, key=lambda p: p.mastery or 0)
        pool = list(s.prerequisite_candidates.get(gap.competency_id, []))
        pick = _first_open(_lessons(pool)) or _latest_done(_lessons(pool))
        if pick is not None:
            return out(REMEDIATE, "prerequisite_gap", pick,
                       f"{st.name} builds on {gap.name}, which is at {_pct(gap.mastery or 0)}; it needs {_pct(gap.required)}.",
                       [Fact("prerequisite", gap.name), Fact("prerequisite_mastery", round(gap.mastery or 0, 4)), Fact("prerequisite_required", gap.required)],
                       competency_id=gap.competency_id, competency_name=gap.name)
        considered.append(f"prerequisite {gap.name} is below {_pct(gap.required)} but no material is mapped to it")

    # ---- repeated typed error: change modality
    wrong = [e for e in recent[:ERROR_WINDOW] if _wrong(e)]
    typed: Dict[str, List[Evidence]] = {}
    for e in wrong:
        if e.error_type and e.error_type != "unknown":
            typed.setdefault(e.error_type, []).append(e)
    repeated = next(((k, v) for k, v in sorted(typed.items(), key=lambda kv: -len(kv[1])) if len(v) >= REPEAT_ERRORS), None)
    if repeated and s.last_consumed_type:
        other = [c for c in lessons if not c.completed and c.content_type != s.last_consumed_type]
        pick = min(other, key=lambda c: c.order) if other else None
        if pick is not None:
            kind, errs = repeated
            return out(CHANGE_MODALITY, "repeated_error_type", pick,
                       f"The same kind of mistake ({kind.replace('_', ' ')}) has come up {len(errs)} times, and the {s.last_consumed_type.lower()} material did not resolve it, so here is a different format.",
                       [Fact("repeated_error", kind, [e.id for e in errs]), Fact("previous_modality", s.last_consumed_type)], considered)
        considered.append("the same mistake keeps recurring but there is no unstudied material in another format")

    # ---- questions were too hard
    last_two = recent[:2]
    if mastery < STRUGGLE_BELOW and len(last_two) == 2 and all(_wrong(e) and (e.difficulty or 0) >= HARD_QUESTION for e in last_two):
        easy = [c for c in lessons if not c.completed and (c.difficulty is None or c.difficulty < HARD_QUESTION)]
        pick = min(easy, key=lambda c: (c.difficulty if c.difficulty is not None else 1.0, c.order)) if easy else None
        if pick is not None:
            return out(EASIER, "too_hard", pick,
                       "Your last two answers were on hard questions and were incorrect, so here is a more foundational step first.",
                       [Fact("recent_difficulties", [e.difficulty for e in last_two], [e.id for e in last_two])], considered)
        considered.append("the last two questions were hard, but no easier unstudied material exists")

    # ---- struggling
    latest = recent[0] if recent else None
    latest_content = _latest_done(lessons)
    content_since = bool(latest and latest_content and latest_content.completed_at and latest_content.completed_at > latest.occurred_at)
    if mastery < STRUGGLE_BELOW and latest is not None and _wrong(latest) and not content_since:
        pick = _first_open(lessons)
        if pick is not None:
            return out(REMEDIATE, "struggling", pick,
                       f"Your recent answers on {st.name} were mostly incorrect (mastery {_pct(mastery)}), so a short lesson comes before the next assessment.", (), considered)
        if latest_content is not None:
            return out(REVISIT, "struggling", latest_content,
                       f"Your recent answers on {st.name} were mostly incorrect (mastery {_pct(mastery)}) and you have seen all of its material; revisit it.", (), considered)
        considered.append("mastery is low but no material is mapped to the competency")
        return out(ASSESS, "struggling", (quizzes[0] if quizzes else None), f"Mastery on {st.name} is {_pct(mastery)}; no lesson material is mapped to it.", (), considered)

    # ---- content done since the last answer, still below target: measure again
    if mastery < target and content_since:
        quiz = _first_open(quizzes) or (quizzes[0] if quizzes else None)
        return out(ASSESS, "reassess_after_content", quiz,
                   f"You completed \"{latest_content.title}\" after your last answer, so a new assessment will show whether {st.name} has improved.",
                   [Fact("content_completed", latest_content.title), Fact("content_completed_at", latest_content.completed_at.isoformat())], considered)

    # ---- too little evidence
    if st.confidence < LOW_CONFIDENCE:
        quiz = _first_open(quizzes) or (quizzes[0] if quizzes else None)
        return out(ASSESS, "low_confidence", quiz,
                   f"The estimate for {st.name} rests on only {st.evidence_count} answer(s), so more evidence is needed before deciding what to do.", (), considered)

    # ---- declining
    if st.trend == "declining":
        pick = latest_content or _first_open(lessons)
        if pick is not None:
            return out(REVISIT, "declining", pick, f"Your mastery of {st.name} has been falling, so it is worth revisiting.", (), considered)

    # ---- mastered: skip ahead
    if mastery >= SKIP_MASTERY and st.confidence >= SKIP_CONFIDENCE and _streak(recent) >= SKIP_STREAK:
        ahead = _first_open(s.next_competency_candidates)
        if ahead is not None:
            skipped = [c for c in lessons if not c.completed]
            return out(SKIP, "mastered_streak", ahead,
                       f"You have answered the last {_streak(recent)} questions on {st.name} correctly (mastery {_pct(mastery)}), so the remaining introductory material can be skipped.",
                       [Fact("streak", _streak(recent), [e.id for e in recent[:_streak(recent)]]), Fact("skipped_items", [c.title for c in skipped])], considered)

    # ---- above target: harder
    accuracy = sum(e.signal for e in recent[:5]) / len(recent[:5]) if recent else 0.0
    if mastery >= target and accuracy >= HARDER_ACCURACY and len(recent) >= 3:
        pool = [c for c in quizzes if c.difficulty is not None]
        harder = [c for c in pool if c.difficulty is not None and c.difficulty >= (recent[0].difficulty or 0.0)]
        pick = min(harder, key=lambda c: (c.completed, -(c.difficulty or 0), c.order)) if harder else None
        if pick is not None:
            return out(HARDER, "above_target", pick,
                       f"You are above target on {st.name} ({_pct(mastery)}) with {round(accuracy * 100)}% recent accuracy, so the next step is a more demanding assessment.",
                       [Fact("recent_accuracy", round(accuracy, 3))], considered)

    # ---- default
    nxt = _first_open(lessons) or _first_open(quizzes)
    if nxt is None:
        nxt = _first_open(s.next_competency_candidates)
        return out(CONTINUE, "default", nxt,
                   f"You have completed everything mapped to {st.name}." + (" Here is the next step in your course." if nxt else ""), (), considered)
    return out(CONTINUE, "default", nxt, f"You are progressing on {st.name} (mastery {_pct(mastery)}); here is the next step.", (), considered)


# ------------------------------------------------------------------------------------------------ the explanation
def explain(d: Decision) -> Dict[str, Any]:
    """The 'Why am I seeing this?' text, built only from the facts of the decision."""
    lines: List[str] = []
    ids: List[str] = []
    for f in d.facts:
        ids.extend(f.evidence_ids)
    by = {f.label: f for f in d.facts}
    if "recent_incorrect" in by and "recent_answers" in by and by["recent_incorrect"].value:
        lines.append(f"{by['recent_incorrect'].value} of your last {by['recent_answers'].value} answers were incorrect")
    for label, fact in by.items():
        if label.startswith("error:"):
            lines.append(f"{fact.value} answer{'s' if fact.value != 1 else ''} with a {label[6:].replace('_', ' ')} error")
    if "latest_answer_at" in by:
        lines.append("Latest answer: " + datetime.fromisoformat(str(by["latest_answer_at"].value)).strftime("%b %d, %H:%M UTC"))
    if "streak" in by:
        lines.append(f"{by['streak'].value} correct answers in a row")
    if "prerequisite" in by:
        lines.append(f"Prerequisite {by['prerequisite'].value}: {round(float(by['prerequisite_mastery'].value) * 100)}% (needs {round(float(by['prerequisite_required'].value) * 100)}%)")
    if "content_completed" in by:
        lines.append(f"You completed \"{by['content_completed'].value}\" since your last answer")
    return {
        "headline": d.reason,
        "evidence": lines,
        "mastery": by["mastery"].value if "mastery" in by else None,
        "confidence": by["confidence"].value if "confidence" in by else None,
        "evidence_ids": sorted(set(ids)),
        "rule": d.rule,
        "considered": d.considered,
    }
