"""
Content Recommender Module.
Resolves curriculum content items matching pedagogical policy recommendations.
"""
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, asc

from app.models.tables import Module, ContentItem


async def find_recommended_content(
    db: AsyncSession,
    org_id: UUID,
    course_id: UUID,
    recommended_difficulty: str,
    decision: str,
    current_module_id: Optional[UUID] = None,
) -> Optional[Dict[str, Any]]:
    """
    Selects the most suitable content item based on the adaptive policy decision.
    """
    # Query candidate modules in the course
    module_query = select(Module).where(
        and_(Module.org_id == org_id, Module.course_id == course_id)
    ).order_by(asc(Module.sequence_order))
    
    module_res = await db.execute(module_query)
    modules = module_res.scalars().all()

    if not modules:
        return None

    # Pick targeted module
    target_module = modules[0]
    if current_module_id:
        for idx, m in enumerate(modules):
            if m.id == current_module_id:
                if decision == "advance" and idx + 1 < len(modules):
                    target_module = modules[idx + 1]
                elif decision == "remediate" or decision == "revisit":
                    target_module = m
                else:
                    target_module = m
                break

    # Look for content item in target module matching difficulty
    content_query = select(ContentItem).where(
        and_(ContentItem.org_id == org_id, ContentItem.module_id == target_module.id)
    ).order_by(asc(ContentItem.sort_order))

    content_res = await db.execute(content_query)
    content_items = content_res.scalars().all()

    if not content_items:
        return {
            "module_id": str(target_module.id),
            "module_title": target_module.title,
            "content_id": None,
            "content_title": None,
            "difficulty": target_module.difficulty,
        }

    # Match difficulty preference if available
    matched_content = next(
        (c for c in content_items if c.difficulty == recommended_difficulty),
        content_items[0]
    )

    return {
        "module_id": str(target_module.id),
        "module_title": target_module.title,
        "content_id": str(matched_content.id),
        "content_title": matched_content.title,
        "difficulty": matched_content.difficulty,
    }
