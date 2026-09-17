"""
AI Insights API Gateway Router.
Proxies to the Reporting Engine with multi-tenant isolation and RBAC.
"""

from typing import Optional, Dict, Any, List
from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_current_tenant, require_roles, TenantContext
from app.models import User
from app.core.config import settings
from shared.contracts.contracts import InsightGenerateRequest, InsightResponse

router = APIRouter(prefix="/insights", tags=["Grounded AI Insights"])


@router.post("/generate", response_model=InsightResponse)
async def generate_insight(
    payload: InsightGenerateRequest,
    report_type: str = Query("progress_summary"),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """
    Synthesize an evidence-grounded AI narrative report with verifiable source citations.
    """
    if payload.scope_type == "learner" and current_user.role == "learner" and payload.scope_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Learners can only generate insights for their own profile",
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.reporting_engine_url}/api/v1/insights/generate",
                params={"org_id": str(tenant_ctx.org_id), "report_type": report_type},
                json=payload.model_dump(mode="json"),
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Reporting Engine error: {resp.text}",
                )
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reporting Engine unreachable: {str(exc)}",
        )


@router.get("/{insight_id}")
async def get_insight_detail(
    insight_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Retrieve saved AI insight with verified citations."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.reporting_engine_url}/api/v1/insights/{insight_id}",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reporting Engine unreachable: {str(exc)}",
        )


@router.get("/{insight_id}/evidence")
async def get_insight_evidence_facts(
    insight_id: UUID,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
):
    """Retrieve backing evidence facts for an insight's claims."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.reporting_engine_url}/api/v1/insights/{insight_id}/evidence",
                params={"org_id": str(tenant_ctx.org_id)},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reporting Engine unreachable: {str(exc)}",
        )
