"""
API v1 Router Aggregator.
"""

from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.organizations import router as orgs_router
from app.api.v1.users import router as users_router
from app.api.v1.courses import router as courses_router
from app.api.v1.assignments import router as assignments_router
from app.api.v1.competencies import router as competencies_router
from app.api.v1.enrollments import router as enrollments_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.ai import router as ai_router
from app.api.v1.events import router as events_router
from app.api.v1.learning_sessions import router as learning_sessions_router
from app.api.v1.adaptive import router as adaptive_router
from app.api.v1.teams import router as teams_router
from app.api.v1.risks import router as risks_router
from app.api.v1.insights import router as insights_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.reports import router as reports_router
from app.api.v1.export import router as export_router
from app.api.v1.embed import router as embed_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(orgs_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(teams_router)
api_v1_router.include_router(courses_router)
api_v1_router.include_router(assignments_router)
api_v1_router.include_router(competencies_router)
api_v1_router.include_router(enrollments_router)
api_v1_router.include_router(ingestion_router)
api_v1_router.include_router(ai_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(learning_sessions_router)
api_v1_router.include_router(adaptive_router)
api_v1_router.include_router(risks_router)
api_v1_router.include_router(insights_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(export_router)
api_v1_router.include_router(embed_router)
