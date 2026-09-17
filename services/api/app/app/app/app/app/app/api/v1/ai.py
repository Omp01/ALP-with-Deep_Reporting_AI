"""
AI Derivation and Assessment Generation Endpoints.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models import (
    Competency,
    Course,
    CourseCompetency,
    Module,
    ContentItem,
    AssessmentItem,
    User,
)
from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext, log_audit_action
from app.services.ai_service import ai_generation_service

router = APIRouter(prefix="/ai", tags=["AI Derivation & Generation"])


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------
class DeriveCompetenciesRequest(BaseModel):
    text: str = Field(..., min_length=20, description="Raw instructional text or syllabus")
    course_id: Optional[UUID] = None
    save_to_course: bool = False


class GenerateAssessmentsRequest(BaseModel):
    module_id: UUID
    competency_id: UUID
    count: int = Field(2, ge=1, le=5)
    auto_approve: bool = True


class AssessmentReviewRequest(BaseModel):
    quality_flag: str = Field(..., description="approved, flagged, rejected")


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/derive-competencies")
async def derive_competencies(
    payload: DeriveCompetenciesRequest,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract Bloom-aligned competencies from instructional text or syllabus.
    Optionally persists them directly to the target course.
    """
    course_code = "GEN"
    course = None
    if payload.course_id:
        c_res = await db.execute(
            select(Course).where(and_(Course.id == payload.course_id, Course.org_id == tenant_ctx.org_id))
        )
        course = c_res.scalar_one_or_none()
        if course:
            course_code = course.code

    derived = await ai_generation_service.derive_competencies_from_text(payload.text, course_code)

    saved_items = []
    if payload.save_to_course and course:
        for item in derived:
            # Check if code exists
            existing = await db.execute(
                select(Competency).where(and_(Competency.org_id == tenant_ctx.org_id, Competency.code == item["code"]))
            )
            comp = existing.scalar_one_or_none()
            if not comp:
                comp = Competency(
                    id=uuid.uuid4(),
                    org_id=tenant_ctx.org_id,
                    name=item["name"],
                    code=item["code"],
                    description=item.get("description", ""),
                    taxonomy_level=item.get("taxonomy_level", "understand"),
                )
                db.add(comp)
                await db.flush()

            # Map to course
            mapping_res = await db.execute(
                select(CourseCompetency).where(
                    and_(CourseCompetency.course_id == course.id, CourseCompetency.competency_id == comp.id)
                )
            )
            if not mapping_res.scalar_one_or_none():
                db.add(CourseCompetency(course_id=course.id, competency_id=comp.id, target_mastery=0.80))
            
            saved_items.append({"id": str(comp.id), "code": comp.code, "name": comp.name})
        await db.flush()

    return {
        "derived_competencies": derived,
        "saved_count": len(saved_items),
        "saved_items": saved_items,
    }


@router.post("/generate-assessments", status_code=status.HTTP_201_CREATED)
async def generate_assessment_items(
    payload: GenerateAssessmentsRequest,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Synthesize psychometric assessment questions with difficulty and discrimination parameters.
    """
    # Verify module
    mod_res = await db.execute(
        select(Module).where(and_(Module.id == payload.module_id, Module.org_id == tenant_ctx.org_id))
    )
    module = mod_res.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    # Verify competency
    comp_res = await db.execute(
        select(Competency).where(and_(Competency.id == payload.competency_id, Competency.org_id == tenant_ctx.org_id))
    )
    competency = comp_res.scalar_one_or_none()
    if not competency:
        raise HTTPException(status_code=404, detail="Competency not found")

    # Aggregate module text content
    items_res = await db.execute(select(ContentItem).where(ContentItem.module_id == module.id))
    content_items = items_res.scalars().all()
    aggregated_text = "\n\n".join([ci.raw_text or "" for ci in content_items if ci.raw_text])
    if not aggregated_text.strip():
        aggregated_text = f"{module.title}: {module.description or ''}\nCompetency: {competency.description or ''}"

    generated_raw = await ai_generation_service.generate_assessment_items(
        content_text=aggregated_text,
        competency_name=competency.name,
        competency_id=competency.id,
        module_id=module.id,
        count=payload.count,
    )

    created_records = []
    for item in generated_raw:
        record = AssessmentItem(
            id=uuid.uuid4(),
            org_id=tenant_ctx.org_id,
            module_id=module.id,
            competency_id=competency.id,
            question_text=item["question_text"],
            question_type=item.get("question_type", "multiple_choice"),
            options=item.get("options", []),
            correct_answer=item.get("correct_answer", {"answer": "a"}),
            explanation=item.get("explanation", ""),
            difficulty_score=item.get("difficulty_score", 0.5),
            discrimination_index=item.get("discrimination_index", 1.0),
            is_ai_generated=True,
            quality_flag="approved" if payload.auto_approve else "flagged",
        )
        db.add(record)
        created_records.append(record)

    await db.flush()

    return [
        {
            "id": str(r.id),
            "module_id": str(r.module_id),
            "competency_id": str(r.competency_id),
            "question_text": r.question_text,
            "question_type": r.question_type,
            "options": r.options,
            "difficulty_score": r.difficulty_score,
            "discrimination_index": r.discrimination_index,
            "is_ai_generated": r.is_ai_generated,
            "quality_flag": r.quality_flag,
        }
        for r in created_records
    ]


@router.put("/assessments/{item_id}/review")
async def review_assessment_item(
    item_id: UUID,
    payload: AssessmentReviewRequest,
    current_user: User = Depends(require_roles(["instructor", "org_admin"])),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update review status (approved, flagged, rejected) of an assessment item."""
    res = await db.execute(
        select(AssessmentItem).where(and_(AssessmentItem.id == item_id, AssessmentItem.org_id == tenant_ctx.org_id))
    )
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Assessment item not found")

    item.quality_flag = payload.quality_flag
    await db.flush()
    return {"id": str(item.id), "quality_flag": item.quality_flag, "status": "updated"}


@router.get("/assessments")
async def list_assessment_items(
    module_id: Optional[UUID] = None,
    competency_id: Optional[UUID] = None,
    quality_flag: Optional[str] = None,
    is_ai_generated: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=100),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List question bank items with psychometric filters."""
    query = select(AssessmentItem).where(AssessmentItem.org_id == tenant_ctx.org_id)
    if module_id:
        query = query.where(AssessmentItem.module_id == module_id)
    if competency_id:
        query = query.where(AssessmentItem.competency_id == competency_id)
    if quality_flag:
        query = query.where(AssessmentItem.quality_flag == quality_flag)
    if is_ai_generated is not None:
        query = query.where(AssessmentItem.is_ai_generated == is_ai_generated)

    query = query.order_by(AssessmentItem.created_at.desc()).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return [
        {
            "id": str(i.id),
            "module_id": str(i.module_id),
            "competency_id": str(i.competency_id),
            "question_text": i.question_text,
            "question_type": i.question_type,
            "options": i.options,
            "difficulty_score": i.difficulty_score,
            "discrimination_index": i.discrimination_index,
            "is_ai_generated": i.is_ai_generated,
            "quality_flag": i.quality_flag,
        }
        for i in items
    ]
