"""
Generating a report: authorise the scope, build the evidence package, ask the model to interpret it, validate every claim, store.

    scope check (who may ask about whom)  ->  evidence package (deterministic)  ->  findings as claims (deterministic)
        ->  reporting agent (optional, interpretation only)  ->  citation validation  ->  stored report

Findings from `Package.patterns` are always in the report. Model claims are added only if they pass validation. A model outage or a
malformed answer leaves a report with the findings and an honest `ai_status`.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import effective_roles
from app.core.config import settings
from app.core.rbac import Role, has_any_role
from app.events import queries as event_queries
from app.models import Report, Team, User, UserTeam
from app.reporting import agent, builders, validator
from app.reporting.package import Package

logger = logging.getLogger("api.reporting")
AUDIENCES = ("learner", "team", "ld", "organization")


class ReportError(Exception):
    code = "report_error"
    status_code = 400

    def __init__(self, message: str, code: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


def _is_admin(viewer: User) -> bool:
    return has_any_role(effective_roles(viewer), [Role.LD_ADMIN, Role.ORG_ADMIN])


async def scope_members(db: AsyncSession, org_id: UUID, viewer: User, team_id: Optional[UUID]) -> tuple:
    """(member ids or None for everyone, label) for a team report, or a refusal."""
    visible = await event_queries.visible_user_ids(db, viewer, org_id)
    if team_id is None:
        return visible, "All learners in your remit"
    team = (await db.execute(select(Team).where(Team.id == team_id, Team.org_id == org_id))).scalar_one_or_none()
    if team is None or (visible is not None and team.manager_id != viewer.id):
        raise ReportError("Team not found", "team_not_found", 404)
    members = set((await db.execute(select(UserTeam.user_id).where(UserTeam.team_id == team_id, UserTeam.org_id == org_id))).scalars())
    return (members if visible is None else members & visible), team.name


async def build_package(db: AsyncSession, org_id: UUID, viewer: User, audience: str, scope_id: Optional[UUID], days: Optional[int]) -> Package:
    if audience not in AUDIENCES:
        raise ReportError(f"audience must be one of: {', '.join(AUDIENCES)}", "invalid_audience", 422)
    start, end = builders.window(days)
    roles = effective_roles(viewer)
    if audience == "learner":
        target_id = scope_id or viewer.id
        visible = await event_queries.visible_user_ids(db, viewer, org_id)
        user = (await db.execute(select(User).where(User.id == target_id, User.org_id == org_id))).scalar_one_or_none()
        if user is None or (visible is not None and target_id not in visible):
            raise ReportError("Learner not found", "learner_not_found", 404)
        return await builders.build_learner(db, org_id, user, start, end)
    if audience == "team":
        if not has_any_role(roles, [Role.MANAGER, Role.LD_ADMIN, Role.ORG_ADMIN]):
            raise ReportError("Team reports are for managers and administrators.", "forbidden", 403)
        members, label = await scope_members(db, org_id, viewer, scope_id)
        return await builders.build_team(db, org_id, members, scope_id, label, start, end)
    if not _is_admin(viewer):
        raise ReportError("This report is for L&D and organization administrators.", "forbidden", 403)
    return await (builders.build_ld(db, org_id, start, end) if audience == "ld" else builders.build_organization(db, org_id, start, end))


def deterministic_claims(pkg: Package) -> List[Dict[str, Any]]:
    return [{"claim": p["statement"], "claim_type": p["claim_type"], "evidence_ids": p["evidence_ids"], "metric_ids": p["metric_ids"], "confidence": p["confidence"],
             "source": "deterministic", "pattern_id": p["pattern_id"] if "pattern_id" in p else p["id"], "subject": p["subject"], "kind": p["kind"], "priority": p["priority"],
             "scope": pkg.scope_label, "timestamp": pkg.end.isoformat()} for p in sorted(pkg.patterns, key=lambda p: p["priority"])]


def deterministic_summary(pkg: Package) -> Optional[str]:
    top = sorted(pkg.patterns, key=lambda p: p["priority"])[:3]
    if not top:
        return None
    return f"{len(pkg.patterns)} finding(s) for {pkg.scope_label}. Most important: " + " ".join(p["statement"] for p in top)


def _out(report: Report, cached: bool = False) -> Dict[str, Any]:
    return {
        "id": str(report.id), "audience": report.audience, "scope": report.package["report_scope"], "generated_by": report.generated_by, "ai_status": report.ai_status,
        "ai_note": report.ai_note, "model": report.model, "summary": report.summary, "claims": report.claims, "rejected_claims": report.rejected_claims,
        "notes": report.package.get("notes", []), "metrics": list(report.package["metrics"].values()), "created_at": report.created_at.isoformat(), "cached": cached,
        "counts": {"records": len(report.package["records"]), "metrics": len(report.package["metrics"]), "findings": len(report.package["patterns"]),
                   "accepted": len(report.claims), "rejected": len(report.rejected_claims)},
    }


async def generate(db: AsyncSession, *, org_id: UUID, viewer: User, audience: str, scope_id: Optional[UUID] = None, days: Optional[int] = None,
                   use_ai: bool = True, force: bool = False) -> Dict[str, Any]:
    pkg = await build_package(db, org_id, viewer, audience, scope_id, days)
    digest = pkg.content_hash()
    if not force:
        recent = (await db.execute(select(Report).where(
            Report.org_id == org_id, Report.audience == audience, Report.package_hash == digest, Report.requested_by_id == viewer.id,
            Report.created_at >= datetime.utcnow() - timedelta(minutes=settings.reporting_cache_minutes)).order_by(Report.created_at.desc()).limit(1))).scalar_one_or_none()
        if recent is not None and (not use_ai or recent.ai_status in ("ok", "skipped")):
            logger.info("report_cached", extra={"audience": audience, "report_id": str(recent.id)})
            return _out(recent, cached=True)

    package = pkg.to_dict()
    org = str(org_id)
    base = validator.validate_all(deterministic_claims(pkg), package, org)
    accepted, rejected = base["accepted"], base["rejected"]

    ai_status, ai_note, model = "skipped", None, None
    summary = deterministic_summary(pkg)
    generated_by = "deterministic"
    if use_ai:
        result = await agent.run(pkg)
        ai_status, ai_note = result.status, result.note
        if result.out is not None:
            model = result.model
            verdicts = validator.validate_all([{**c.model_dump(), "source": "ai", "scope": pkg.scope_label, "timestamp": pkg.end.isoformat()} for c in result.out.claims], package, org)
            accepted += verdicts["accepted"]
            rejected += verdicts["rejected"]
            if result.out.summary and not validator.validate_narrative(result.out.summary, package):
                summary, generated_by = result.out.summary, "ai"
            elif result.out.summary:
                ai_note = "The model's summary contained numbers or wording the evidence does not support and was replaced by a deterministic one."
            if not verdicts["accepted"] and result.out.claims:
                ai_note = (ai_note + " " if ai_note else "") + "None of the model's claims passed citation validation."
            if verdicts["accepted"] and generated_by == "deterministic":
                generated_by = "ai"
    logger.info("report_generated", extra={"audience": audience, "org_id": org, "accepted": len(accepted), "rejected": len(rejected), "ai_status": ai_status})

    report = Report(org_id=org_id, audience=audience, scope_type=pkg.scope_type, scope_id=pkg.scope_id, period_start=pkg.start, period_end=pkg.end, requested_by_id=viewer.id,
                    generated_by=generated_by, ai_status=ai_status, ai_note=ai_note, model=model, prompt_version=agent.PROMPT_VERSION if use_ai else None, package_hash=digest,
                    package=package, summary=summary, claims=accepted, rejected_claims=rejected)
    db.add(report)
    await db.flush()
    return _out(report)


async def load(db: AsyncSession, org_id: UUID, viewer: User, report_id: UUID) -> Report:
    report = (await db.execute(select(Report).where(Report.id == report_id, Report.org_id == org_id))).scalar_one_or_none()
    if report is None:
        raise ReportError("Report not found", "report_not_found", 404)
    if report.requested_by_id != viewer.id:
        # someone else's report is visible only within the remit that would have let them ask for it
        try:
            await build_authorisation(db, org_id, viewer, report)
        except ReportError:
            raise ReportError("Report not found", "report_not_found", 404)
    return report


async def build_authorisation(db: AsyncSession, org_id: UUID, viewer: User, report: Report) -> None:
    roles = effective_roles(viewer)
    if report.audience in ("ld", "organization"):
        if not _is_admin(viewer):
            raise ReportError("forbidden", "forbidden", 403)
    elif report.audience == "team":
        if not has_any_role(roles, [Role.MANAGER, Role.LD_ADMIN, Role.ORG_ADMIN]):
            raise ReportError("forbidden", "forbidden", 403)
        if not _is_admin(viewer):
            await scope_members(db, org_id, viewer, report.scope_id)
    else:
        visible = await event_queries.visible_user_ids(db, viewer, org_id)
        if visible is not None and report.scope_id not in visible:
            raise ReportError("forbidden", "forbidden", 403)


def evidence_detail(report: Report, evidence_id: str) -> Dict[str, Any]:
    """One cited record as stored with the report, plus links to the live source."""
    rec = report.package["records"].get(evidence_id)
    if rec is None or rec.get("org_id") != str(report.org_id):
        raise ReportError("Evidence not found in this report", "evidence_not_found", 404)
    kind, _, raw = evidence_id.partition("_")
    links = {"evidence": f"/api/v1/mastery/evidence/{raw}"}.get(kind)
    citing = [c["claim"] for c in report.claims if evidence_id in c.get("evidence_ids", [])]
    return {**rec, "source_link": links, "cited_by": citing}
