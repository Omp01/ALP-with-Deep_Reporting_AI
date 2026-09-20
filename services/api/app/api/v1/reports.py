"""
Grounded reports (docs/REPORTING_AI.md): four audiences, cited claims, evidence drawer, scheduled digests, BI JSON.

    POST /reports/generate                      build the evidence package, interpret it, validate every claim, store
    GET  /reports                               reports you may see (newest first)
    GET  /reports/{id}                          one report with its claims (accepted), refused claims and metrics
    GET  /reports/{id}/evidence/{evidence_id}   one cited record as stored with the report (the evidence drawer)

    GET  /reports/learner|team|ld|organization  the evidence package as structured JSON, no model (for BI tools)
    GET  /reports/skill-gaps  /risks  /evidence structured JSON

    POST /reports/schedules, GET /reports/schedules, POST /reports/schedules/{id}/run, POST /reports/schedules/run-due
    GET  /reports/digests                       stored digests you may see
    POST /reports/digest/generate, GET /reports/digest/latest   on-demand weekly team digest (kept path)

Nothing in a report is shown unless its citations validated. Reports are scoped like the data they describe.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, effective_roles, get_current_tenant, get_current_user, get_db, log_audit_action, require_roles
from app.api.v1 import mastery as mastery_api
from app.competency import insight
from app.core.rbac import Role, has_any_role
from app.events import queries as event_queries
from app.models import EvidenceRecord, LearnerRisk, Report, ReportDigest, ScheduledReport, User
from app.reporting import service as reporting

router = APIRouter(prefix="/reports", tags=["Grounded Reports"])
_ADMINS = ["ld_admin", "org_admin"]


def _fail(exc: reporting.ReportError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


class GenerateRequest(BaseModel):
    audience: str = Field(..., description="learner | team | ld | organization")
    scope_id: Optional[UUID] = Field(None, description="learner id (learner) or team id (team); default: yourself / everyone in your remit")
    days: Optional[int] = Field(None, ge=1, le=365)
    use_ai: bool = True
    force: bool = Field(False, description="ignore a recent identical report")


@router.post("/generate")
async def generate_report(payload: GenerateRequest, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                          db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        result = await reporting.generate(db, org_id=tenant_ctx.org_id, viewer=current_user, audience=payload.audience, scope_id=payload.scope_id, days=payload.days,
                                          use_ai=payload.use_ai, force=payload.force)
    except reporting.ReportError as exc:
        _fail(exc)
    if not result["cached"]:
        await log_audit_action(db, tenant_ctx.org_id, current_user.id, "REPORT_GENERATED", "REPORT", result["id"], {"audience": payload.audience, "ai_status": result["ai_status"]})
    return result


# ---- BI: the package as JSON, no model ---------------------------------------------------------
async def _package_json(audience: str, scope_id: Optional[UUID], days: Optional[int], user: User, tenant_ctx: TenantContext, db: AsyncSession) -> Dict[str, Any]:
    try:
        return (await reporting.build_package(db, tenant_ctx.org_id, user, audience, scope_id, days)).to_dict()
    except reporting.ReportError as exc:
        _fail(exc)


@router.get("/learner")
async def bi_learner(user_id: Optional[UUID] = None, days: Optional[int] = Query(None, ge=1, le=365), current_user: User = Depends(get_current_user),
                     tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    return await _package_json("learner", user_id, days, current_user, tenant_ctx, db)


@router.get("/team")
async def bi_team(team_id: Optional[UUID] = None, days: Optional[int] = Query(None, ge=1, le=365), current_user: User = Depends(get_current_user),
                  tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    return await _package_json("team", team_id, days, current_user, tenant_ctx, db)


@router.get("/ld")
async def bi_ld(days: Optional[int] = Query(None, ge=1, le=365), current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                db: AsyncSession = Depends(get_db)):
    return await _package_json("ld", None, days, current_user, tenant_ctx, db)


@router.get("/organization")
async def bi_organization(days: Optional[int] = Query(None, ge=1, le=365), current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                          db: AsyncSession = Depends(get_db)):
    return await _package_json("organization", None, days, current_user, tenant_ctx, db)


@router.get("/skill-gaps")
async def bi_skill_gaps(team_id: Optional[UUID] = None, course_id: Optional[UUID] = None, current_user: User = Depends(require_roles(["ld_admin", "org_admin", "manager"])),
                        tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    return await mastery_api.cohort_gaps(team_id, course_id, current_user, tenant_ctx, db)


@router.get("/risks")
async def bi_risks(current_user: User = Depends(require_roles(["ld_admin", "org_admin", "manager"])), tenant_ctx: TenantContext = Depends(get_current_tenant),
                   db: AsyncSession = Depends(get_db)):
    visible = await event_queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    query = select(LearnerRisk).where(LearnerRisk.org_id == tenant_ctx.org_id, LearnerRisk.is_resolved.is_(False))
    if visible is not None:
        query = query.where(LearnerRisk.user_id.in_(list(visible) or [UUID(int=0)]))
    return {"risks": [{"id": str(r.id), "user_id": str(r.user_id), "course_id": str(r.course_id), "level": r.risk_level, "score": r.risk_score, "reasons": r.risk_details or [],
                       "actions": r.recommended_actions, "detected_at": r.detected_at.isoformat(), "updated_at": r.updated_at.isoformat()} for r in (await db.execute(query)).scalars()]}


@router.get("/evidence")
async def bi_evidence(ids: str = Query(..., description="comma-separated evidence record ids (uuid)"), current_user: User = Depends(get_current_user),
                      tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    """Graded-answer evidence by id, for anyone whose remit includes the learner. Each id is checked; the rest are simply absent."""
    wanted: List[UUID] = []
    for raw in ids.split(",")[:100]:
        try:
            wanted.append(UUID(raw.strip().removeprefix("evidence_")))
        except ValueError:
            raise HTTPException(status_code=422, detail={"code": "invalid_id", "message": f"'{raw}' is not an evidence id"})
    visible = await event_queries.visible_user_ids(db, current_user, tenant_ctx.org_id)
    rows = (await db.execute(select(EvidenceRecord).where(EvidenceRecord.org_id == tenant_ctx.org_id, EvidenceRecord.id.in_(wanted)))).scalars().all()
    return {"evidence": [{"id": str(r.id), "user_id": str(r.user_id), "competency_id": str(r.competency_id), "source_type": r.source_type, "signal": r.signal, "confidence": r.confidence,
                          "error_type": r.error_type, "difficulty": r.difficulty, "attempt_number": r.attempt_number, "occurred_at": r.occurred_at.isoformat()}
                         for r in rows if visible is None or r.user_id in visible]}


# ---- stored reports ----------------------------------------------------------------------------
@router.get("")
async def list_reports(audience: Optional[str] = None, limit: int = Query(20, ge=1, le=100), current_user: User = Depends(get_current_user),
                       tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    query = select(Report).where(Report.org_id == tenant_ctx.org_id, Report.requested_by_id == current_user.id).order_by(Report.created_at.desc()).limit(limit)
    if audience:
        query = query.where(Report.audience == audience)
    return {"items": [{"id": str(r.id), "audience": r.audience, "scope": r.package["report_scope"]["scope_label"], "generated_by": r.generated_by, "ai_status": r.ai_status,
                       "created_at": r.created_at.isoformat(), "claims": len(r.claims), "rejected": len(r.rejected_claims)} for r in (await db.execute(query)).scalars()]}


@router.get("/digests")
async def list_digests(limit: int = Query(10, ge=1, le=50), current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                       db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    rows = (await db.execute(select(ReportDigest, ScheduledReport).join(ScheduledReport, ScheduledReport.id == ReportDigest.scheduled_report_id)
                             .where(ReportDigest.org_id == tenant_ctx.org_id).order_by(ReportDigest.sent_at.desc()).limit(200))).all()
    mine = [(d, s) for d, s in rows if any(r.get("user_id") == str(current_user.id) for r in (s.recipients or []))][:limit]
    return {"items": [{"id": str(d.id), "title": s.title, "audience": s.report_type, "generated_at": d.sent_at.isoformat(), "status": d.status, "content": d.generated_content,
                       "report_id": (d.sent_to or [{}])[0].get("report_id") if d.sent_to else None} for d, s in mine]}


# ---- schedules and digests ---------------------------------------------------------------------
CADENCE_DAYS = {"weekly": 7, "monthly": 30}


class ScheduleIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    audience: str = Field(..., description="learner | team | ld | organization")
    cadence: str = Field("weekly", pattern=r"^(weekly|monthly)$")
    scope_id: Optional[UUID] = None


async def _run_schedule(db: AsyncSession, schedule: ScheduledReport, now: datetime) -> Dict[str, Any]:
    owner_id = UUID((schedule.recipients or [{}])[0]["user_id"])
    owner = (await db.execute(select(User).where(User.id == owner_id, User.org_id == schedule.org_id))).scalar_one_or_none()
    if owner is None or not owner.is_active:
        schedule.is_active = False
        return {"schedule_id": str(schedule.id), "status": "failed", "reason": "the owner no longer exists or is inactive"}
    scope_id = UUID(schedule.template_id) if schedule.template_id else None
    days = CADENCE_DAYS[schedule.schedule_cron.lstrip("@")]
    try:
        report = await reporting.generate(db, org_id=schedule.org_id, viewer=owner, audience=schedule.report_type, scope_id=scope_id, days=days, force=True)
        lines = [schedule.title, report["summary"] or "No findings this period."] + [f"- {c['claim']} [{len(c['evidence_ids'])} evidence]" for c in report["claims"][:12]]
        status = "success"
    except reporting.ReportError as exc:
        report, lines, status = {"id": None}, [f"The digest could not be generated: {exc.message}"], "failed"
    db.add(ReportDigest(org_id=schedule.org_id, scheduled_report_id=schedule.id, generated_content="\n".join(lines), status=status,
                        sent_to=[{"user_id": str(owner_id), "channel": "in_app", "report_id": report["id"]}], sent_at=now))
    schedule.last_run_at, schedule.next_run_at = now, now + timedelta(days=days)
    await db.flush()
    return {"schedule_id": str(schedule.id), "status": status, "report_id": report["id"]}


@router.post("/schedules", status_code=201)
async def create_schedule(payload: ScheduleIn, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    try:
        await reporting.build_package(db, tenant_ctx.org_id, current_user, payload.audience, payload.scope_id, 7)      # the same check as generating it: you can only schedule what you may ask for
    except reporting.ReportError as exc:
        _fail(exc)
    now = datetime.utcnow()
    schedule = ScheduledReport(org_id=tenant_ctx.org_id, title=payload.title, report_type=payload.audience, schedule_cron=f"@{payload.cadence}", recipients=[{"user_id": str(current_user.id)}],
                               template_id=str(payload.scope_id) if payload.scope_id else None, next_run_at=now + timedelta(days=CADENCE_DAYS[payload.cadence]), is_active=True)
    db.add(schedule)
    await db.flush()
    return {"id": str(schedule.id), "title": schedule.title, "audience": schedule.report_type, "cadence": payload.cadence, "next_run_at": schedule.next_run_at.isoformat()}


@router.get("/schedules")
async def list_schedules(current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ScheduledReport).where(ScheduledReport.org_id == tenant_ctx.org_id).order_by(ScheduledReport.created_at.desc()))).scalars().all()
    return {"items": [{"id": str(s.id), "title": s.title, "audience": s.report_type, "cadence": s.schedule_cron.lstrip("@"), "is_active": s.is_active,
                       "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None, "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None}
                      for s in rows if any(r.get("user_id") == str(current_user.id) for r in (s.recipients or []))]}


@router.post("/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: UUID, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    schedule = (await db.execute(select(ScheduledReport).where(ScheduledReport.id == schedule_id, ScheduledReport.org_id == tenant_ctx.org_id))).scalar_one_or_none()
    if schedule is None or not any(r.get("user_id") == str(current_user.id) for r in (schedule.recipients or [])):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return await _run_schedule(db, schedule, datetime.utcnow())


@router.post("/schedules/run-due")
async def run_due_schedules(current_user: User = Depends(require_roles(_ADMINS)), tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    due = (await db.execute(select(ScheduledReport).where(ScheduledReport.org_id == tenant_ctx.org_id, ScheduledReport.is_active.is_(True), ScheduledReport.next_run_at <= now))).scalars().all()
    return {"ran": [await _run_schedule(db, s, now) for s in due]}


@router.post("/digest/generate")
async def generate_digest(current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])), tenant_ctx: TenantContext = Depends(get_current_tenant),
                          db: AsyncSession = Depends(get_db)):
    """A weekly team digest now, for the caller's remit."""
    schedule = ScheduledReport(org_id=tenant_ctx.org_id, title="Weekly team digest", report_type="team", schedule_cron="@weekly", recipients=[{"user_id": str(current_user.id)}],
                               next_run_at=datetime.utcnow() + timedelta(days=7), is_active=True)
    db.add(schedule)
    await db.flush()
    return await _run_schedule(db, schedule, datetime.utcnow())


@router.get("/digest/latest")
async def latest_digest(current_user: User = Depends(require_roles(["instructor", "manager", "org_admin", "super_admin"])), tenant_ctx: TenantContext = Depends(get_current_tenant),
                        db: AsyncSession = Depends(get_db)):
    items = (await list_digests(1, current_user, tenant_ctx, db))["items"]
    if not items:
        raise HTTPException(status_code=404, detail="No digest has been generated yet.")
    return items[0]


# ---- one report (last: `/{report_id}` must not swallow the literal paths above)
@router.get("/{report_id}")
async def get_report(report_id: UUID, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    try:
        report = await reporting.load(db, tenant_ctx.org_id, current_user, report_id)
    except reporting.ReportError as exc:
        _fail(exc)
    return reporting._out(report, cached=True)


@router.get("/{report_id}/evidence/{evidence_id}")
async def get_report_evidence(report_id: UUID, evidence_id: str, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                              db: AsyncSession = Depends(get_db)):
    try:
        report = await reporting.load(db, tenant_ctx.org_id, current_user, report_id)
        return reporting.evidence_detail(report, evidence_id)
    except reporting.ReportError as exc:
        _fail(exc)
