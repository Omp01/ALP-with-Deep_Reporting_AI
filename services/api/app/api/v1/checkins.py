"""
Login check-in: an AI-written quiz on the learner's own course material plus a short self-report, scored, with a report.

Everything here is for the signed-in learner about themselves. There is no learner_id anywhere: nobody, whatever their role, can
open somebody else's check-in (the self-report in particular is private to the learner). See docs/CHECKIN.md.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_tenant, get_current_user, get_db
from app.checkin import service
from app.models import User

router = APIRouter(prefix="/checkins", tags=["Login check-in"])


class StartPayload(BaseModel):
    course_id: Optional[UUID] = None
    fresh: bool = Field(True, description="False resumes an unfinished check-in from the last few hours instead of writing a new one")


class SubmitPayload(BaseModel):
    quiz: Dict[str, Optional[str]] = Field(default_factory=dict, description="question id -> chosen option id (null or absent = unanswered)")
    self_report: Dict[str, int] = Field(default_factory=dict, description="statement id -> rating 1-5 (absent = not answered)")
    coaching_note: bool = True


def _raise(exc: service.CheckinError):
    raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message})


@router.post("/start", status_code=202)
async def start_checkin(payload: StartPayload, user: User = Depends(get_current_user), tenant: TenantContext = Depends(get_current_tenant),
                        db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Begin a check-in. Returns immediately: while status is `generating` a model is writing the quiz and the self-report from the
    course material (poll `GET /checkins/{id}`). `failed` carries an honest reason (no course, no model, nothing verified).
    """
    try:
        row = await service.start(db, tenant.org_id, user, payload.course_id, payload.fresh)
    except service.CheckinError as exc:
        _raise(exc)
    return await service.view(db, row)


@router.get("")
async def my_checkins(limit: int = 20, user: User = Depends(get_current_user), tenant: TenantContext = Depends(get_current_tenant),
                      db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    return await service.history(db, tenant.org_id, user.id, max(1, min(limit, 100)))


@router.get("/{checkin_id}")
async def read_checkin(checkin_id: UUID, user: User = Depends(get_current_user), tenant: TenantContext = Depends(get_current_tenant),
                       db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await service.get(db, tenant.org_id, user.id, checkin_id)
    if row is None:
        raise HTTPException(404, detail={"code": "not_found", "message": "Check-in not found."})
    return await service.view(db, row)


@router.post("/{checkin_id}/submit")
async def submit_checkin(checkin_id: UUID, payload: SubmitPayload, user: User = Depends(get_current_user),
                         tenant: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Score the quiz, score the self-report, and return the report. Correct answers and source passages appear only now."""
    try:
        return await service.submit(db, tenant.org_id, user, checkin_id, payload.quiz, payload.self_report, payload.coaching_note)
    except service.CheckinError as exc:
        _raise(exc)


@router.post("/{checkin_id}/skip")
async def skip_checkin(checkin_id: UUID, user: User = Depends(get_current_user), tenant: TenantContext = Depends(get_current_tenant),
                       db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        return await service.skip(db, tenant.org_id, user, checkin_id)
    except service.CheckinError as exc:
        _raise(exc)
