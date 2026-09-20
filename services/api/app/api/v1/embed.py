"""
Embeddable reporting widget (spec section 32).

    POST /embed/tokens                 an authorised person mints a scoped, expiring embed token for one report and one scope
    GET  /embed/data?token=            the report data for that token (the same reporting backend as the app)
    GET  /embed/adaptive-reporting.js  the `<adaptive-report>` custom element that calls the endpoint above

    <script src="https://HOST/api/v1/embed/adaptive-reporting.js"></script>
    <adaptive-report api="https://HOST/api/v1" token="..." report="skill-gaps"></adaptive-report>

An embed token is not an access token: it is refused everywhere except `/embed/data`, it names one report and one scope, it expires,
and every request re-checks that its issuer still exists, is active and may still see that scope. The earlier `/embed/report`
took a learner id and an organization id from the URL with no authentication and returned that learner's competencies; it is gone.
"""

from datetime import timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, effective_roles, get_current_tenant, get_current_user, get_db
from app.competency import insight
from app.core.rbac import Role, has_any_role
from app.core.security import create_access_token, decode_access_token
from app.events import queries as event_queries
from app.models import LearnerRisk, User
from app.reporting import service as reporting

router = APIRouter(prefix="/embed", tags=["Embeddable Widget"])
REPORTS = ("skill-gaps", "risks", "summary")
SCOPES = ("team", "organization", "learner")


class TokenIn(BaseModel):
    report: str = Field(..., description="skill-gaps | risks | summary")
    scope: str = Field(..., description="team | organization | learner")
    scope_id: Optional[UUID] = None
    days_valid: int = Field(30, ge=1, le=90)


def _refuse(exc: reporting.ReportError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


async def _members(db: AsyncSession, org_id: UUID, user: User, scope: str, scope_id: Optional[UUID]):
    """The learner ids a token's scope covers for this issuer (None: the whole organization), or a refusal."""
    if scope == "organization":
        if (await event_queries.visible_user_ids(db, user, org_id)) is not None:
            raise reporting.ReportError("Only administrators may embed organization-wide data.", "forbidden", 403)
        return None
    if scope == "team":
        if not has_any_role(effective_roles(user), [Role.MANAGER, Role.LD_ADMIN, Role.ORG_ADMIN]):
            raise reporting.ReportError("Team data is for managers and administrators.", "forbidden", 403)
        members, _ = await reporting.scope_members(db, org_id, user, scope_id)
        return members
    visible = await event_queries.visible_user_ids(db, user, org_id)
    target = scope_id or user.id
    if visible is not None and target not in visible:
        raise reporting.ReportError("Learner not found", "learner_not_found", 404)
    return {target}


@router.post("/tokens", status_code=201)
async def create_embed_token(payload: TokenIn, current_user: User = Depends(get_current_user), tenant_ctx: TenantContext = Depends(get_current_tenant),
                             db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    if payload.report not in REPORTS or payload.scope not in SCOPES:
        raise HTTPException(status_code=422, detail={"code": "invalid_embed", "message": f"report must be one of {REPORTS} and scope one of {SCOPES}"})
    try:
        await _members(db, tenant_ctx.org_id, current_user, payload.scope, payload.scope_id)
    except reporting.ReportError as exc:
        _refuse(exc)
    token = create_access_token(subject=str(current_user.id), expires_delta=timedelta(days=payload.days_valid), claims={
        "purpose": "embed", "org_id": str(tenant_ctx.org_id), "report": payload.report, "scope": payload.scope, "scope_id": str(payload.scope_id) if payload.scope_id else None})
    return {"token": token, "expires_in_days": payload.days_valid, "report": payload.report, "scope": payload.scope,
            "snippet": f'<script src="/api/v1/embed/adaptive-reporting.js"></script>\n<adaptive-report api="/api/v1" token="{token}" report="{payload.report}"></adaptive-report>'}


@router.get("/data")
async def embed_data(token: str = Query(...), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    claims = decode_access_token(token)
    if not claims or claims.get("purpose") != "embed":
        raise HTTPException(status_code=401, detail={"code": "invalid_embed_token", "message": "The embed token is invalid or has expired."})
    try:
        org_id, user_id = UUID(claims["org_id"]), UUID(claims["sub"])
        scope_id = UUID(claims["scope_id"]) if claims.get("scope_id") else None
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail={"code": "invalid_embed_token", "message": "The embed token is malformed."})
    user = (await db.execute(select(User).where(User.id == user_id, User.org_id == org_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail={"code": "invalid_embed_token", "message": "The embed token's issuer is no longer active."})
    report, scope = claims.get("report"), claims.get("scope")
    try:
        members = await _members(db, org_id, user, scope, scope_id)
        if report == "skill-gaps":
            data = await insight.cohort_gaps(db, org_id, members, None)
            return {"report": report, "scope": scope, "data": data}
        if report == "risks":
            query = select(LearnerRisk.risk_level, func.count(func.distinct(LearnerRisk.user_id))).where(LearnerRisk.org_id == org_id, LearnerRisk.is_resolved.is_(False)).group_by(LearnerRisk.risk_level)
            if members is not None:
                query = query.where(LearnerRisk.user_id.in_(list(members) or [UUID(int=0)]))
            return {"report": report, "scope": scope, "data": {"learners_by_level": {level: n for level, n in (await db.execute(query)).all()}}}
        audience = {"organization": "organization", "team": "team", "learner": "learner"}[scope]
        pkg = await reporting.build_package(db, org_id, user, audience, scope_id if scope != "organization" else None, None)
        return {"report": "summary", "scope": scope, "data": {"scope": pkg.scope(), "findings": [{"statement": p["statement"], "claim_type": p["claim_type"], "evidence": len(p["evidence_ids"])} for p in
                                                                                             sorted(pkg.patterns, key=lambda p: p["priority"])[:6]], "notes": pkg.notes}}
    except reporting.ReportError as exc:
        _refuse(exc)


WIDGET_JS = r"""
(function () {
  if (customElements.get('adaptive-report')) return;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  class AdaptiveReport extends HTMLElement {
    async connectedCallback() {
      const root = this.attachShadow({ mode: 'open' });
      const api = (this.getAttribute('api') || '').replace(/\/$/, '');
      const token = this.getAttribute('token') || '';
      root.innerHTML = '<style>:host{display:block;font:14px system-ui,sans-serif;color:#0f172a;border:1px solid #e2e8f0;border-radius:10px;padding:14px;background:#fff}h3{margin:0 0 8px;font-size:15px}li{margin:4px 0}small{color:#64748b}.bar{height:6px;background:#e2e8f0;border-radius:3px;margin-top:3px}.bar>i{display:block;height:6px;border-radius:3px;background:#f59e0b}</style><small>Loading…</small>';
      try {
        const response = await fetch(api + '/embed/data?token=' + encodeURIComponent(token));
        const body = await response.json();
        if (!response.ok) throw new Error((body.detail && body.detail.message) || 'The report is unavailable.');
        root.innerHTML = root.querySelector('style').outerHTML + this.render(body);
      } catch (error) {
        root.innerHTML = root.querySelector('style').outerHTML + '<small>' + esc(error.message) + '</small>';
      }
    }
    render(body) {
      if (body.report === 'skill-gaps') {
        const rows = (body.data.competencies || []).slice(0, 6).map((c) =>
          '<li><b>' + esc(c.name) + '</b><br><small>' + c.learners_below_target + ' of ' + c.assessed_learners + (c.assessed_learners === 1 ? ' assessed learner is below ' : ' assessed learners are below ') + Math.round(c.target_mastery * 100) + '%</small><div class="bar"><i style="width:' + Math.round(c.share_below_target * 100) + '%"></i></div></li>').join('');
        return '<h3>Skill gaps</h3>' + (rows ? '<ul style="padding-left:18px;margin:0">' + rows + '</ul>' : '<small>No competency has enough graded answers yet.</small>');
      }
      if (body.report === 'risks') {
        const levels = body.data.learners_by_level || {};
        const rows = Object.keys(levels).map((k) => '<li>' + esc(k) + ': ' + levels[k] + ' learner(s)</li>').join('');
        return '<h3>Learners at risk</h3>' + (rows ? '<ul style="padding-left:18px;margin:0">' + rows + '</ul>' : '<small>No open risk alerts.</small>');
      }
      const items = (body.data.findings || []).map((f) => '<li>' + esc(f.statement) + ' <small>(' + f.evidence + ' evidence)</small></li>').join('');
      return '<h3>' + esc(body.data.scope.scope_label) + '</h3>' + (items ? '<ul style="padding-left:18px;margin:0">' + items + '</ul>' : '<small>' + esc((body.data.notes || ['Nothing to report yet.'])[0]) + '</small>');
    }
  }
  customElements.define('adaptive-report', AdaptiveReport);
})();
"""


@router.get("/adaptive-reporting.js")
async def widget_script() -> Response:
    return Response(content=WIDGET_JS, media_type="application/javascript", headers={"Cache-Control": "public, max-age=300"})
