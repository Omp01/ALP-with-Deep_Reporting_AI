"""
Builders of the four evidence packages. Everything here is a query and arithmetic: no model, no randomness.

    learner        one learner's own competencies, changes, mistakes, decisions and activity
    team           the learners a manager is responsible for: counts per competency, who is stuck, who is improving, who is at risk
                   (no raw activity: no event lists, no session times)
    ld             content effectiveness, where learners get stuck, competencies without enough content, assessments as evidence
    organization   competency strength across the tenant, coverage, and where risk concentrates

Findings ("patterns") are computed here with the sentence and the numbers; a language model may explain them, never change them.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Set
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.competency import bkt, insight
from app.core.config import settings
from app.models import (
    AdaptiveDecision, Competency, CompetencyStateUpdate, ContentCompetency, ContentItem, ContentProgress, Course, CourseCompetency, Enrollment, EvidenceRecord,
    LearnerCompetency, LearnerRisk, LearningEvent, LearningSession, QuestionResponse, Quiz, QuizQuestion, Team, User, UserTeam,
)
from app.reporting.package import Package, pct

IMPROVING_BY = 0.10
STUCK_BELOW = 0.50
STUCK_MIN_EVIDENCE = 4
INACTIVE_DAYS = 7
MAX_RECORDS_PER_COMPETENCY = 8


def _names(items: Sequence[str], limit: int = 4) -> str:
    return ", ".join(items[:limit]) + (f" and {len(items) - limit} more" if len(items) > limit else "")


def window(days: Optional[int], end: Optional[datetime] = None):
    end = end or datetime.utcnow()
    return end - timedelta(days=days or settings.reporting_period_days), end


async def _states(db: AsyncSession, org_id: UUID, user_ids: Optional[Set[UUID]]):
    query = (select(LearnerCompetency, Competency).join(Competency, Competency.id == LearnerCompetency.competency_id)
             .where(LearnerCompetency.org_id == org_id, LearnerCompetency.basis == "evidence", LearnerCompetency.data_points_count > 0))
    if user_ids is not None:
        query = query.where(LearnerCompetency.user_id.in_(list(user_ids) or [UUID(int=0)]))
    return (await db.execute(query)).all()


async def _targets(db: AsyncSession, org_id: UUID) -> Dict[UUID, float]:
    rows = (await db.execute(select(CourseCompetency.competency_id, func.max(CourseCompetency.target_mastery)).join(Course, Course.id == CourseCompetency.course_id)
                             .where(Course.org_id == org_id).group_by(CourseCompetency.competency_id))).all()
    return {cid: float(t) for cid, t in rows}


async def _updates(db: AsyncSession, org_id: UUID, user_ids: Optional[Set[UUID]], start: datetime, end: datetime):
    query = (select(CompetencyStateUpdate, EvidenceRecord).join(EvidenceRecord, EvidenceRecord.id == CompetencyStateUpdate.evidence_id)
             .where(CompetencyStateUpdate.org_id == org_id, EvidenceRecord.occurred_at >= start, EvidenceRecord.occurred_at <= end)
             .order_by(CompetencyStateUpdate.user_id, CompetencyStateUpdate.competency_id, CompetencyStateUpdate.sequence))
    if user_ids is not None:
        query = query.where(CompetencyStateUpdate.user_id.in_(list(user_ids) or [UUID(int=0)]))
    return (await db.execute(query)).all()


def _change(updates: Sequence) -> Optional[Dict[str, Any]]:
    """Net movement over a run of updates (in sequence order): from the first previous value (the prior when there was none) to the last new one."""
    if not updates:
        return None
    first, last = updates[0][0], updates[-1][0]
    before = first.previous_mastery if first.previous_mastery is not None else bkt.MasteryParams().prior
    return {"from": round(before, 4), "to": round(last.new_mastery, 4), "delta": round(last.new_mastery - before, 4), "n": len(updates)}


# =============================================================================================================== learner
async def build_learner(db: AsyncSession, org_id: UUID, user: User, start: datetime, end: datetime) -> Package:
    pkg = Package(org_id, "learner", "learner", user.id, user.full_name, start, end)
    targets = await _targets(db, org_id)
    states = await _states(db, org_id, {user.id})
    updates = await _updates(db, org_id, {user.id}, start, end)
    by_comp: Dict[UUID, List] = defaultdict(list)
    for pair in updates:
        by_comp[pair[0].competency_id].append(pair)
    questions = await _question_text(db, [e.response_id for _, e in updates if e.response_id])

    total_answers = total_wrong = total_retries = 0
    for state, comp in sorted(states, key=lambda sc: sc[1].name):
        target = targets.get(comp.id, 0.70)
        sid = pkg.record("state", state.id, f"{comp.name}: competency state", {
            "competency": comp.name, "competency_id": str(comp.id), "mastery": round(state.mastery_score, 4), "confidence": round(state.confidence_score, 4), "trend": state.trend,
            "trend_delta": state.trend_delta, "evidence_count": state.data_points_count, "correct": state.correct_count, "incorrect": state.incorrect_count,
            "error_distribution": state.error_distribution or {}, "target": target}, state.last_assessed_at, user.id)
        m_mastery = pkg.metric(f"{comp.id}_mastery", f"{comp.name}: mastery", round(state.mastery_score, 4), "probability", "Current estimate from the competency engine", [sid])
        mine = by_comp.get(comp.id, [])
        ev_ids = []
        for update, evidence in mine[-MAX_RECORDS_PER_COMPETENCY:]:
            q = questions.get(evidence.response_id)
            eid = pkg.record("evidence", evidence.id, f"{comp.name}: graded answer", {
                "competency": comp.name, "signal": evidence.signal, "confidence": evidence.confidence, "error_type": evidence.error_type, "difficulty": evidence.difficulty,
                "attempt_number": evidence.attempt_number, "source_type": evidence.source_type, "question": q, "evidence_quote": evidence.evidence_quote}, evidence.occurred_at, user.id)
            uid = pkg.record("update", update.id, f"{comp.name}: mastery update", {
                "competency": comp.name, "previous_mastery": update.previous_mastery, "new_mastery": update.new_mastery, "signal": update.signal, "weight": update.weight,
                "evidence_id": str(evidence.id), "method": update.method, "note": update.note}, evidence.occurred_at, user.id)
            ev_ids += [eid, uid]
        change = _change(mine)
        wrong = [e for _, e in mine if e.signal < 0.5]
        total_answers, total_wrong = total_answers + len(mine), total_wrong + len(wrong)
        total_retries += sum(1 for _, e in mine if (e.attempt_number or 1) > 1)
        if change:
            m_change = pkg.metric(f"{comp.id}_change", f"{comp.name}: change in mastery over the period", change["delta"], "probability points", "Last new mastery minus the first previous mastery in the period", ev_ids)
            m_n = pkg.metric(f"{comp.id}_answers", f"{comp.name}: graded answers in the period", change["n"], "answers", "Evidence records in the period", ev_ids)
            if change["delta"] >= IMPROVING_BY and change["n"] >= 3:
                pkg.pattern("improving", f"Mastery of {comp.name} rose from {pct(change['from'])} to {pct(change['to'])} across {change['n']} graded answers in this period.",
                            [m_change, m_n, m_mastery], ev_ids + [sid], subject=comp.name, priority=3)
            elif change["delta"] <= -IMPROVING_BY and change["n"] >= 3:
                pkg.pattern("declining", f"Mastery of {comp.name} fell from {pct(change['from'])} to {pct(change['to'])} across {change['n']} graded answers in this period.",
                            [m_change, m_n, m_mastery], ev_ids + [sid], subject=comp.name, priority=1)
        typed = Counter(e.error_type for e in wrong if e.error_type and e.error_type != "unknown")
        for kind, n in typed.items():
            if n >= 2:
                m_err = pkg.metric(f"{comp.id}_error_{kind}", f"{comp.name}: {kind.replace('_', ' ')} errors", n, "answers", "Incorrect answers in the period with this error type",
                                   [pkg_id for pkg_id in [f"evidence_{e.id}" for e in wrong if e.error_type == kind]])
                pkg.pattern("repeated_error", f"{n} of the incorrect answers on {comp.name} in this period were of the {kind.replace('_', ' ')} kind.", [m_err, m_n] if change else [m_err],
                            [f"evidence_{e.id}" for e in wrong if e.error_type == kind] + [sid], subject=comp.name, priority=2)
        if state.data_points_count >= 2 and state.mastery_score < target:
            m_target = pkg.metric(f"{comp.id}_target", f"{comp.name}: target mastery", target, "probability", "The highest target set for this competency by a course")
            pkg.pattern("weak", f"{comp.name} is at {pct(state.mastery_score)} against a target of {pct(target)}, from {state.data_points_count} graded answers in total.",
                        [m_mastery, m_target], [sid] + ev_ids[:4], subject=comp.name, priority=2)
        elif state.mastery_score >= target and state.data_points_count >= 3:
            m_target = pkg.metric(f"{comp.id}_target", f"{comp.name}: target mastery", target, "probability", "The highest target set for this competency by a course")
            pkg.pattern("strong", f"{comp.name} is at {pct(state.mastery_score)}, at or above its target of {pct(target)}.", [m_mastery, m_target], [sid], subject=comp.name, priority=4)

    decisions = (await db.execute(select(AdaptiveDecision).where(AdaptiveDecision.org_id == org_id, AdaptiveDecision.user_id == user.id, AdaptiveDecision.created_at >= start,
                                                                 AdaptiveDecision.created_at <= end, AdaptiveDecision.decision_metadata["engine"].astext == "adaptive_v1")
                                  .order_by(AdaptiveDecision.created_at.desc()).limit(5))).scalars().all()
    for d in decisions:
        name = (d.decision_metadata.get("content") or {}).get("title")
        pkg.record("decision", d.id, "Adaptive decision", {"action": d.decision_type.upper(), "rule": d.rule_applied, "reason": d.reason, "content": name}, d.created_at, user.id)
    if decisions:
        d = decisions[0]
        name = (d.decision_metadata.get("content") or {}).get("title")
        pkg.pattern("next_step", f"The latest adaptive recommendation is {d.decision_type.upper()}" + (f': "{name}".' if name else "."), [], [f"decision_{d.id}"], claim_type="OBSERVATION", priority=3)

    sessions = (await db.execute(select(LearningSession).where(LearningSession.org_id == org_id, LearningSession.user_id == user.id, LearningSession.started_at >= start,
                                                              LearningSession.started_at <= end).order_by(LearningSession.started_at.desc()).limit(20))).scalars().all()
    session_ids = [pkg.record("session", s.id, "Learning session", {"started_at": s.started_at, "last_activity_at": s.last_activity_at, "ended": s.ended_at is not None}, s.started_at, user.id) for s in sessions]
    active_days = len({s.started_at.date() for s in sessions})
    m_days = pkg.metric("active_days", "Days with a learning session", active_days, "days", "Distinct days on which a session started in the period", session_ids)
    m_answers = pkg.metric("answers", "Graded answers in the period", total_answers, "answers", "Evidence records in the period")
    pkg.metric("incorrect", "Incorrect answers in the period", total_wrong, "answers", "Evidence with signal below 0.5")
    last = (await db.execute(select(func.max(LearningEvent.timestamp)).where(LearningEvent.org_id == org_id, LearningEvent.user_id == user.id, LearningEvent.event_type.in_(insight.ACTIVITY_TYPES)))).scalar()
    if last is not None and (end - last).days >= INACTIVE_DAYS:
        m_idle = pkg.metric("days_since_activity", "Days since last learning activity", (end - last).days, "days", "Days between the last learner activity event and the end of the period")
        pkg.pattern("inactive", f"There has been no learning activity for {(end - last).days} days.", [m_idle], session_ids[:1] or [], priority=2)
    if not states:
        pkg.notes.append("No graded answers exist for this learner yet, so no competency can be reported.")
    return pkg


async def _question_text(db: AsyncSession, response_ids: Sequence[UUID]) -> Dict[UUID, str]:
    if not response_ids:
        return {}
    rows = (await db.execute(select(QuestionResponse.id, QuizQuestion.question_text).join(QuizQuestion, QuizQuestion.id == QuestionResponse.question_id)
                             .where(QuestionResponse.id.in_(list(set(response_ids)))))).all()
    return {rid: text for rid, text in rows}


# ================================================================================================================ team
async def build_team(db: AsyncSession, org_id: UUID, member_ids: Optional[Set[UUID]], scope_id: Optional[UUID], label: str, start: datetime, end: datetime) -> Package:
    pkg = Package(org_id, "team", "team", scope_id, label, start, end)
    targets = await _targets(db, org_id)
    rows = await _states(db, org_id, member_ids)
    users = {u.id: u for u in (await db.execute(select(User).where(User.org_id == org_id, User.id.in_(list({s.user_id for s, _ in rows}) or [UUID(int=0)])))).scalars()}
    updates = await _updates(db, org_id, member_ids, start, end)
    grouped: Dict[tuple, List] = defaultdict(list)
    for pair in updates:
        grouped[(pair[0].user_id, pair[0].competency_id)].append(pair)
    learners = {s.user_id for s, _ in rows}
    pkg.metric("learners_with_evidence", "Learners with graded evidence", len(learners), "learners", "Learners in scope with at least one graded answer")

    by_comp: Dict[UUID, List] = defaultdict(list)
    for state, comp in rows:
        by_comp[comp.id].append((state, comp))
    stuck_all, improving_all = [], []
    for comp_id, items in sorted(by_comp.items(), key=lambda kv: kv[1][0][1].name):
        comp = items[0][1]
        target = targets.get(comp_id, 0.70)
        assessed = [(s, c) for s, c in items if s.data_points_count >= 2]
        if not assessed:
            continue
        state_ids = {s.id: pkg.record("state", s.id, f"{comp.name}: {users[s.user_id].full_name if s.user_id in users else 'learner'}",
                                      {"competency": comp.name, "mastery": round(s.mastery_score, 4), "trend": s.trend, "evidence_count": s.data_points_count, "target": target,
                                       "learner": users[s.user_id].full_name if s.user_id in users else None}, s.last_assessed_at, s.user_id) for s, _ in assessed}
        below = [s for s, _ in assessed if s.mastery_score < target]
        declining = [s for s, _ in assessed if s.trend == "declining"]
        changes = {s.user_id: _change(grouped.get((s.user_id, comp_id), [])) for s, _ in assessed}
        improving = [s for s, _ in assessed if changes[s.user_id] and changes[s.user_id]["delta"] >= IMPROVING_BY and changes[s.user_id]["n"] >= 2]
        m_assessed = pkg.metric(f"{comp_id}_assessed", f"{comp.name}: assessed learners", len(assessed), "learners", "Learners with at least two graded answers", [state_ids[s.id] for s, _ in assessed])
        m_below = pkg.metric(f"{comp_id}_below", f"{comp.name}: learners below target", len(below), "learners", f"Assessed learners whose mastery is below the target of {pct(target)}", [state_ids[s.id] for s in below])
        m_target = pkg.metric(f"{comp_id}_target", f"{comp.name}: target mastery", target, "probability", "The highest target set for this competency by a course")
        if below:
            pkg.pattern("cohort_gap", f"{len(below)} of {len(assessed)} assessed learners have {comp.name} mastery below {pct(target)}.", [m_below, m_assessed, m_target],
                        [state_ids[s.id] for s in below], subject=comp.name, priority=1 if len(below) * 2 >= len(assessed) else 2)
        if declining:
            m_dec = pkg.metric(f"{comp_id}_declining", f"{comp.name}: learners with a declining trend", len(declining), "learners", "Assessed learners whose mastery trend is declining", [state_ids[s.id] for s in declining])
            pkg.pattern("negative_trend", f"{len(declining)} of {len(assessed)} assessed learners show a declining trend in {comp.name}.", [m_dec, m_assessed], [state_ids[s.id] for s in declining], subject=comp.name, priority=2)
        if improving:
            m_imp = pkg.metric(f"{comp_id}_improving", f"{comp.name}: learners whose mastery rose", len(improving), "learners", f"Assessed learners whose mastery rose by at least {IMPROVING_BY:.2f} in the period", [state_ids[s.id] for s in improving])
            pkg.pattern("improving", f"{len(improving)} of {len(assessed)} assessed learners raised their {comp.name} mastery by at least {IMPROVING_BY:.2f} in this period.", [m_imp, m_assessed], [state_ids[s.id] for s in improving], subject=comp.name, priority=3)
        for s, _ in assessed:
            if s.mastery_score < STUCK_BELOW and s.data_points_count >= STUCK_MIN_EVIDENCE and s.trend != "improving":
                stuck_all.append((users[s.user_id].full_name if s.user_id in users else "A learner", comp.name, state_ids[s.id]))
    if stuck_all:
        m_stuck = pkg.metric("stuck_learners", "Learners who look stuck", len({n for n, _, _ in stuck_all}), "learners",
                             f"Learners below {pct(STUCK_BELOW)} with at least {STUCK_MIN_EVIDENCE} graded answers whose trend is not improving", [i for _, _, i in stuck_all])
        by_name: Dict[str, List[str]] = defaultdict(list)
        for name, comp, _ in stuck_all:
            by_name[name].append(comp)
        pkg.pattern("stuck", f"{len(by_name)} learner(s) look stuck below {pct(STUCK_BELOW)}: " + _names([f"{n} ({_names(c, 2)})" for n, c in by_name.items()]) + ".",
                    [m_stuck], [i for _, _, i in stuck_all], subject="team", priority=1)

    risks = (await db.execute(select(LearnerRisk, User, Course).join(User, User.id == LearnerRisk.user_id).join(Course, Course.id == LearnerRisk.course_id)
                              .where(LearnerRisk.org_id == org_id, LearnerRisk.is_resolved.is_(False), LearnerRisk.risk_level.in_(("high", "critical")),
                                     *( [LearnerRisk.user_id.in_(list(member_ids) or [UUID(int=0)])] if member_ids is not None else [] )))).all()
    risk_ids = [pkg.record("risk", r.id, f"Risk: {u.full_name}", {"learner": u.full_name, "course": c.title, "level": r.risk_level, "points": sum(d.get("points", 0) for d in (r.risk_details or [])),
                                                                 "reasons": [d.get("description") for d in (r.risk_details or [])]}, r.updated_at, u.id) for r, u, c in risks]
    if risks:
        m_risk = pkg.metric("at_risk_learners", "Learners at high or critical risk", len({u.id for _, u, _ in risks}), "learners", "Unresolved risk alerts at high or critical level", risk_ids)
        pkg.pattern("at_risk", f"{len({u.id for _, u, _ in risks})} learner(s) have an unresolved high or critical risk alert: " + _names(sorted({u.full_name for _, u, _ in risks})) + ".",
                    [m_risk], risk_ids, subject="team", priority=1)
    if not rows:
        pkg.notes.append("No graded answers exist for the learners in this scope yet.")
    return pkg


# ================================================================================================================== ld
async def build_ld(db: AsyncSession, org_id: UUID, start: datetime, end: datetime) -> Package:
    pkg = Package(org_id, "ld", "organization", None, "Learning programme", start, end)
    min_learners = settings.reporting_min_learners_for_content
    items = (await db.execute(select(ContentItem).join(Course, Course.id == ContentItem.course_id).where(ContentItem.org_id == org_id, ContentItem.status == "published", Course.status == "published",
                                                                                                    ContentItem.content_type.notin_(["QUIZ", "ASSIGNMENT"])))).scalars().all()
    mapped: Dict[UUID, Set[UUID]] = defaultdict(set)
    for cid, comp in (await db.execute(select(ContentCompetency.content_item_id, ContentCompetency.competency_id).where(ContentCompetency.content_item_id.in_([i.id for i in items] or [UUID(int=0)])))).all():
        mapped[cid].add(comp)
    progress = defaultdict(list)
    for p in (await db.execute(select(ContentProgress).where(ContentProgress.org_id == org_id, ContentProgress.content_item_id.in_([i.id for i in items] or [UUID(int=0)])))).scalars():
        progress[p.content_item_id].append(p)
    all_updates = defaultdict(list)          # (user, competency) -> [(occurred_at, new_mastery)]
    for update, evidence in await _updates(db, org_id, None, datetime(2000, 1, 1), end):
        all_updates[(update.user_id, update.competency_id)].append((evidence.occurred_at, update.previous_mastery, update.new_mastery))
    comp_names = {c.id: c.name for c in (await db.execute(select(Competency).where(Competency.org_id == org_id))).scalars()}

    for item in items:
        rows = progress.get(item.id, [])
        exposed = [p for p in rows if p.status in ("in_progress", "completed")]
        done = [p for p in rows if p.status == "completed" and p.completed_at]
        if len(exposed) < min_learners:
            continue
        deltas, learners_measured = [], set()
        for p in done:
            for comp in mapped.get(item.id, ()):
                series = sorted(all_updates.get((p.user_id, comp), []))
                before = [m for t, prev, m in series if t <= p.completed_at]
                after = [m for t, prev, m in series if p.completed_at < t <= end]
                if before and after:
                    deltas.append(after[-1] - before[-1])
                    learners_measured.add(p.user_id)
        cid = pkg.record("content", item.id, item.title, {"title": item.title, "content_type": item.content_type, "competencies": [comp_names.get(c) for c in mapped.get(item.id, ())],
                                                       "exposed": len(exposed), "completed": len(done), "learners_measured": len(learners_measured)}, None)
        m_exp = pkg.metric(f"{item.id}_exposed", f"{item.title}: learners exposed", len(exposed), "learners", "Learners with progress on this item", [cid])
        m_done = pkg.metric(f"{item.id}_completed", f"{item.title}: learners who completed it", len(done), "learners", "Learners who completed it", [cid])
        if len(learners_measured) >= min_learners:
            avg = round(sum(deltas) / len(deltas), 4)
            m_delta = pkg.metric(f"{item.id}_delta", f"{item.title}: observed mastery change after completion", avg, "probability points",
                                 "Average of (mastery after the last answer since completion) minus (mastery at completion) over completers with answers on both sides", [cid])
            m_n = pkg.metric(f"{item.id}_measured", f"{item.title}: completers measured", len(learners_measured), "learners", "Completers with graded answers before and after completing it", [cid])
            direction = "higher" if avg > 0 else "lower" if avg < 0 else "unchanged"
            pkg.pattern("content_effectiveness", f"{len(learners_measured)} learners who completed \"{item.title}\" showed {direction} subsequent mastery ({avg:+.2f} on average). This is an observed association and does not establish that the content caused it.",
                        [m_delta, m_n, m_exp, m_done], [cid], claim_type="CORRELATION", subject=item.title, priority=2)
        else:
            pkg.pattern("content_exposure", f"{len(exposed)} learners opened \"{item.title}\" and {len(done)} completed it; too few have graded answers on both sides of it to say anything about its effect.",
                        [m_exp, m_done], [cid], subject=item.title, priority=5)

    # where learners get stuck: questions with many incorrect answers
    wrong_expr = func.sum(case((EvidenceRecord.signal < 0.5, 1), else_=0))
    q_rows = (await db.execute(
        select(QuizQuestion.id, QuizQuestion.question_text, Quiz.title, func.count(EvidenceRecord.id), wrong_expr)
        .join(QuestionResponse, QuestionResponse.question_id == QuizQuestion.id).join(EvidenceRecord, EvidenceRecord.response_id == QuestionResponse.id).join(Quiz, Quiz.id == QuizQuestion.quiz_id)
        .where(EvidenceRecord.org_id == org_id, EvidenceRecord.occurred_at >= start, EvidenceRecord.occurred_at <= end).group_by(QuizQuestion.id, QuizQuestion.question_text, Quiz.title)
    )).all()
    stuck = sorted([(qid, text, quiz, int(n), int(w or 0)) for qid, text, quiz, n, w in q_rows if n >= settings.reporting_min_responses_per_question and (w or 0) / n >= 0.5], key=lambda r: -(r[4] / r[3]))[:5]
    for qid, text, quiz, n, wrong in stuck:
        rid = pkg.record("question", qid, f"Question in {quiz}", {"question": text, "quiz": quiz, "answers": n, "incorrect": wrong}, None)
        m_a = pkg.metric(f"{qid}_answers", "Graded answers to the question", n, "answers", "Evidence records for this question in the period", [rid])
        m_w = pkg.metric(f"{qid}_incorrect", "Incorrect answers to the question", wrong, "answers", "Evidence with signal below 0.5", [rid])
        pkg.pattern("stuck_point", f"{wrong} of {n} graded answers to \"{text[:90]}\" in \"{quiz}\" were incorrect.", [m_w, m_a], [rid], subject=quiz, priority=1)

    # coverage: course competencies with too little material
    course_comps = (await db.execute(select(Competency, Course).join(CourseCompetency, CourseCompetency.competency_id == Competency.id).join(Course, Course.id == CourseCompetency.course_id)
                                     .where(Competency.org_id == org_id, Course.status == "published"))).all()
    lesson_counts = Counter()
    assess_counts = Counter()
    for cid, comps in mapped.items():
        for c in comps:
            lesson_counts[c] += 1
    for qcomp, n in (await db.execute(select(QuizQuestion.competency_id, func.count()).join(Quiz, Quiz.id == QuizQuestion.quiz_id).where(Quiz.org_id == org_id, QuizQuestion.competency_id.is_not(None)).group_by(QuizQuestion.competency_id))).all():
        assess_counts[qcomp] = n
    thin = [(c, course) for c, course in course_comps if lesson_counts[c.id] == 0 or assess_counts[c.id] == 0]
    if thin:
        names = sorted({c.name for c, _ in thin})
        rids = [pkg.record("coverage", c.id, f"Coverage: {c.name}", {"competency": c.name, "course": course.title, "lessons": lesson_counts[c.id], "assessment_questions": assess_counts[c.id]}, None) for c, course in thin]
        m = pkg.metric("thin_competencies", "Competencies without enough content", len(names), "competencies", "Course competencies with no lesson mapped, or no assessment question", rids)
        pkg.pattern("coverage_gap", f"{len(names)} competencies lack either mapped lessons or assessment questions: {_names(names)}.", [m], rids, subject="coverage", priority=2)
    if not pkg.patterns:
        pkg.notes.append("There is not yet enough learner activity across content to report on effectiveness.")
    return pkg


# ========================================================================================================= organization
async def build_organization(db: AsyncSession, org_id: UUID, start: datetime, end: datetime) -> Package:
    pkg = Package(org_id, "organization", "organization", org_id, "Organization", start, end)
    targets = await _targets(db, org_id)
    rows = await _states(db, org_id, None)
    learners = {s.user_id for s, _ in rows}
    pkg.metric("learners_with_evidence", "Learners with graded evidence", len(learners), "learners", "Learners with at least one graded answer")
    by_comp: Dict[UUID, List] = defaultdict(list)
    for s, c in rows:
        if s.data_points_count >= 2:
            by_comp[c.id].append((s, c))
    strong, weak = [], []
    for cid, items in by_comp.items():
        comp, target = items[0][1], targets.get(cid, 0.70)
        masteries = [s.mastery_score for s, _ in items]
        below = [s for s, _ in items if s.mastery_score < target]
        sid = [pkg.record("state", s.id, f"{comp.name} state", {"competency": comp.name, "mastery": round(s.mastery_score, 4), "target": target}, s.last_assessed_at, s.user_id) for s, _ in items][:30]
        m_a = pkg.metric(f"{cid}_assessed", f"{comp.name}: assessed learners", len(items), "learners", "Learners with at least two graded answers", sid)
        m_b = pkg.metric(f"{cid}_below", f"{comp.name}: learners below target", len(below), "learners", f"Assessed learners below the target of {pct(target)}", sid)
        m_med = pkg.metric(f"{cid}_median", f"{comp.name}: median mastery", round(median(masteries), 4), "probability", "Median mastery of assessed learners", sid)
        share = len(below) / len(items)
        (weak if share >= 0.5 else strong if share == 0 else []).append((comp.name, share, len(below), len(items), [m_b, m_a, m_med], sid))
    for name, share, b, n, mids, sid in sorted(weak, key=lambda w: -w[1])[:5]:
        pkg.pattern("capability_gap", f"{b} of {n} assessed learners are below target on {name}.", mids, sid, subject=name, priority=1)
    if strong:
        names = sorted(n for n, *_ in strong)
        pkg.pattern("capability_strength", f"Every assessed learner is at or above target on {_names(names)}.", [m for _, _, _, _, ms, _ in strong for m in ms[:2]], [i for *_, sid in strong for i in sid[:3]], subject="strengths", priority=4)

    # insufficient coverage
    ld = await build_ld(db, org_id, start, end)
    for p in ld.patterns:
        if p["kind"] == "coverage_gap":
            for rid in p["evidence_ids"]:
                pkg.records[rid] = ld.records[rid]
            for mid in p["metric_ids"]:
                pkg.metrics[mid] = ld.metrics[mid]
            pkg.pattern("coverage_gap", p["statement"], p["metric_ids"], p["evidence_ids"], subject="coverage", priority=2)

    # where risk concentrates: by course and by team
    risks = (await db.execute(select(LearnerRisk, Course, User).join(Course, Course.id == LearnerRisk.course_id).join(User, User.id == LearnerRisk.user_id)
                              .where(LearnerRisk.org_id == org_id, LearnerRisk.is_resolved.is_(False)))).all()
    if risks:
        total = len(risks)
        high = [(r, c, u) for r, c, u in risks if r.risk_level in ("high", "critical")]
        by_course = Counter(c.title for _, c, _ in high)
        teams = {(ut.user_id): t.name for ut, t in (await db.execute(select(UserTeam, Team).join(Team, Team.id == UserTeam.team_id).where(Team.org_id == org_id))).all()}
        by_team = Counter(teams.get(u.id, "No team") for _, _, u in high)
        rids = [pkg.record("risk", r.id, "Risk alert", {"course": c.title, "level": r.risk_level, "team": teams.get(u.id, "No team")}, r.updated_at) for r, c, u in high]
        m_high = pkg.metric("high_risk_alerts", "High or critical risk alerts", len(high), "alerts", "Unresolved alerts at high or critical level", rids)
        m_all = pkg.metric("risk_alerts", "Unresolved risk alerts", total, "alerts", "Unresolved alerts of any level")
        if high:
            top_team, top_n = by_team.most_common(1)[0]
            top_course, top_c = by_course.most_common(1)[0]
            pkg.pattern("risk_concentration", f"{top_n} of {len(high)} high or critical risk alerts belong to the {top_team} team, and {top_c} concern the course \"{top_course}\".", [m_high, m_all], rids, subject="risk", priority=1)
    if not pkg.patterns:
        pkg.notes.append("There is not yet enough graded evidence across the organization to report on capability.")
    return pkg
