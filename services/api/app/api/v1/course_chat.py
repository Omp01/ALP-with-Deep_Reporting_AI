"""
Course AI Chatbot & Personalized Learning Path Router.
Allows learners to get AI-powered course summaries, personalized study paths,
and interactive tutoring grounded in course curriculum and learner competencies.
"""

import json
import logging
import re
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import (
    Course,
    Module,
    ContentItem,
    User,
    CourseCompetency,
    Competency,
    LearnerCompetency,
)
from app.models.progress import ContentProgress
from app.api.deps import get_current_user, get_current_tenant, TenantContext
from shared.schemas.ai_provider import (
    get_ai_provider,
    AIMessage,
    AICompletionRequest,
    AIProviderError,
)

logger = logging.getLogger("api.course_chat")

router = APIRouter(prefix="/courses", tags=["Course AI Chatbot"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class CourseChatRequest(BaseModel):
    message: str = Field(..., description="Learner's prompt or question")
    action: Optional[str] = Field("chat", description="'chat', 'summarize', 'learning_path', or 'explain'")
    current_item_id: Optional[UUID] = None
    history: Optional[List[ChatMessage]] = Field(default_factory=list)


class LearningPathStep(BaseModel):
    module_id: str
    module_title: str
    status: str  # "completed", "in_progress", "recommended_next", "up_next"
    rationale: str
    recommended_item_id: Optional[str] = None
    recommended_item_title: Optional[str] = None


class CourseChatResponse(BaseModel):
    reply: str
    action: str
    provider: str
    model: str
    learning_path: Optional[List[LearningPathStep]] = None


# ---------------------------------------------------------------------------
# Helper: Extract structured learning path JSON from LLM output
# ---------------------------------------------------------------------------

def _extract_learning_path(text: str) -> Optional[List[LearningPathStep]]:
    match = re.search(r"```json:learning_path\s*([\s\S]*?)\s*```", text)
    if not match:
        match = re.search(r"```json\s*(\[\s*\{[\s\S]*?\"module_id\"[\s\S]*?\}\s*\])\s*```", text)

    if match:
        try:
            raw_data = json.loads(match.group(1).strip())
            if isinstance(raw_data, list):
                steps = []
                for s in raw_data:
                    steps.append(LearningPathStep(
                        module_id=str(s.get("module_id", "")),
                        module_title=str(s.get("module_title", "Module")),
                        status=str(s.get("status", "up_next")),
                        rationale=str(s.get("rationale", "")),
                        recommended_item_id=str(s.get("recommended_item_id", "")) if s.get("recommended_item_id") else None,
                        recommended_item_title=str(s.get("recommended_item_title", "")) if s.get("recommended_item_title") else None,
                    ))
                return steps
        except Exception as e:
            logger.debug(f"Failed to parse learning_path JSON from LLM response: {e}")
    return None


def _clean_reply_text(text: str) -> str:
    """Removes the raw json:learning_path block from the human-readable reply."""
    cleaned = re.sub(r"```json:learning_path\s*[\s\S]*?\s*```", "", text)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Fallback Generators (Offline / API quota safety)
# ---------------------------------------------------------------------------

def _generate_fallback_summary(course: Course, modules: List[Module], competencies: List[Competency]) -> str:
    comp_bullets = "\n".join([f"- **{c.name}** ({c.taxonomy_level}): {c.description or 'Core skill'}" for c in competencies[:6]])
    mod_bullets = "\n".join([
        f"- **Module {idx + 1}: {m.title}** ({len(m.content_items)} lessons) — {m.description or 'Covers foundational and practical concepts.'}"
        for idx, m in enumerate(modules)
    ])

    return f"""## 🎓 Course Overview: {course.title}

{course.description or 'A comprehensive curriculum designed to build deep, verified competency.'}

### 🎯 Key Learning Objectives & Competencies:
{comp_bullets if comp_bullets else '- Master core concepts and hands-on diagnostic application.'}

### 📚 Curriculum Structure:
{mod_bullets}

### 💡 How to Succeed:
Proceed through each module sequentially, test your understanding on the diagnostic assessments, and monitor your competency mastery in the Skill Mastery portfolio.
"""


def _generate_fallback_learning_path(
    course: Course,
    modules: List[Module],
    progress_map: Dict[UUID, ContentProgress],
    competencies: List[Competency],
    mastery_map: Dict[UUID, LearnerCompetency],
) -> tuple[str, List[LearningPathStep]]:
    steps: List[LearningPathStep] = []
    first_incomplete_found = False

    for idx, m in enumerate(modules):
        total_items = len(m.content_items)
        completed_items = sum(1 for it in m.content_items if progress_map.get(it.id) and progress_map[it.id].status == "completed")

        rec_item = next((it for it in m.content_items if not (progress_map.get(it.id) and progress_map[it.id].status == "completed")), None)
        if not rec_item and m.content_items:
            rec_item = m.content_items[0]

        if completed_items == total_items and total_items > 0:
            status_str = "completed"
            rationale = "All lessons completed and verified."
        elif not first_incomplete_found:
            status_str = "recommended_next"
            rationale = f"Current focal point ({completed_items}/{total_items} complete). Progress through this module to build core competency."
            first_incomplete_found = True
        else:
            status_str = "up_next"
            rationale = "Sequential prerequisite path following current module."

        steps.append(LearningPathStep(
            module_id=str(m.id),
            module_title=m.title,
            status=status_str,
            rationale=rationale,
            recommended_item_id=str(rec_item.id) if rec_item else None,
            recommended_item_title=rec_item.title if rec_item else None,
        ))

    narrative = f"""## 🎯 Personalized Learning Path for {course.title}

Based on your current telemetry and module completion:

1. **Current Milestone:** You are currently progressing through **{next((s.module_title for s in steps if s.status == 'recommended_next'), modules[0].title if modules else 'Module 1')}**.
2. **Pedagogical Recommendation:** Focus on active diagnostic assessments to solidify your Bayesian mastery score.
3. **Sequence:** Follow the prioritized milestones shown below.
"""
    return narrative, steps


# ---------------------------------------------------------------------------
# Endpoint: POST /api/v1/courses/{course_id}/chat
# ---------------------------------------------------------------------------

@router.post("/{course_id}/chat", response_model=CourseChatResponse)
async def chat_with_course_ai(
    course_id: UUID,
    payload: CourseChatRequest,
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    In-Course AI Chatbot & Personalized Learning Path Mentor.
    Answers learner queries, summarizes course material, and computes tailored study paths.
    """
    # 1. Fetch Course with Modules and Content Items
    q = (
        select(Course)
        .options(
            selectinload(Course.modules).selectinload(Module.content_items)
        )
        .where(
            and_(Course.id == course_id, Course.org_id == tenant_ctx.org_id)
        )
    )
    res = await db.execute(q)
    course = res.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    sorted_modules = sorted(course.modules, key=lambda m: getattr(m, "sequence_order", 0))
    all_content_items: List[ContentItem] = []
    for m in sorted_modules:
        m.content_items.sort(key=lambda ci: getattr(ci, "order_index", 0))
        all_content_items.extend(m.content_items)


    item_ids = [ci.id for ci in all_content_items]

    # 2. Fetch Learner Progress
    progress_map: Dict[UUID, ContentProgress] = {}
    if item_ids:
        prog_res = await db.execute(
            select(ContentProgress).where(
                and_(
                    ContentProgress.user_id == current_user.id,
                    ContentProgress.content_item_id.in_(item_ids),
                )
            )
        )
        for cp in prog_res.scalars().all():
            progress_map[cp.content_item_id] = cp

    # 3. Fetch Course Competencies & Learner Mastery
    comp_res = await db.execute(
        select(Competency, CourseCompetency.target_mastery)
        .join(CourseCompetency, CourseCompetency.competency_id == Competency.id)
        .where(CourseCompetency.course_id == course_id)
    )
    competencies_target = comp_res.all()
    comp_ids = [comp.id for comp, _ in competencies_target]
    competencies_list = [comp for comp, _ in competencies_target]

    learner_competency_map: Dict[UUID, LearnerCompetency] = {}
    if comp_ids:
        lc_res = await db.execute(
            select(LearnerCompetency).where(
                and_(
                    LearnerCompetency.user_id == current_user.id,
                    LearnerCompetency.competency_id.in_(comp_ids),
                )
            )
        )
        for lc in lc_res.scalars().all():
            learner_competency_map[lc.competency_id] = lc

    # 4. Construct Grounded Curriculum Context
    module_breakdown = []
    for idx, m in enumerate(sorted_modules):
        items_summary = []
        for it in m.content_items:
            p = progress_map.get(it.id)
            stat = p.status if p else "not_started"
            items_summary.append(f"  - Lesson: {it.title} (type: {it.content_type}, status: {stat})")

        completed_in_mod = sum(1 for it in m.content_items if progress_map.get(it.id) and progress_map[it.id].status == "completed")
        module_breakdown.append(
            f"Module {idx + 1}: {m.title} (ID: {m.id})\n"
            f"Description: {m.description or 'N/A'}\n"
            f"Progress: {completed_in_mod}/{len(m.content_items)} completed\n"
            f"Lessons:\n" + ("\n".join(items_summary) if items_summary else "  - No published items")
        )

    comp_summary = []
    for comp, target_m in competencies_target:
        lc = learner_competency_map.get(comp.id)
        current_m = round(lc.mastery_score, 2) if lc else 0.0
        status_txt = lc.status if lc else "novice"
        comp_summary.append(f"- {comp.name} (Taxonomy: {comp.taxonomy_level}): Learner Mastery = {current_m*100}% (Status: {status_txt}, Target Benchmark: {target_m*100}%)")

    total_lessons = len(all_content_items)
    total_completed = sum(1 for it in all_content_items if progress_map.get(it.id) and progress_map[it.id].status == "completed")
    overall_progress_pct = round((total_completed / total_lessons) * 100, 1) if total_lessons > 0 else 0.0

    system_prompt = f"""You are the intelligent AI Course Mentor & Pedagogical Tutor for the course "{course.title}" ({course.code}) on Adaptive LMS.
Your mission is to provide clear, helpful, accurate, and encouraging guidance to the student ({current_user.full_name or 'Learner'}).

### Course Verified Curriculum:
- Course: {course.title}
- Description: {course.description or 'N/A'}
- Level: {getattr(course, 'difficulty', 'All Levels')}
- Total Lessons: {total_lessons}
- Student Completed: {total_completed} ({overall_progress_pct}%)


### Modules in Syllabus:
{chr(10).join(module_breakdown)}

### Target Competencies & Student Mastery:
{chr(10).join(comp_summary) if comp_summary else '- No explicit mapped competencies'}

### Pedagogical Rules:
1. When asked to "summarize" the course, present a high-yield, structured summary with Objectives, Module Breakdown, Key Competencies, and Advice for Success.
2. When asked for a "learning path", evaluate their completed lessons and competency mastery scores:
   - Identify which module they should focus on next (recommended_next).
   - Flag any competencies where mastery is low (< 0.70) that need review.
   - Provide a motivating step-by-step narrative.
   - MANDATORY: Always conclude with a structured JSON block formatted exactly as:
```json:learning_path
[
  {{
    "module_id": "string-uuid",
    "module_title": "Module Title",
    "status": "completed | in_progress | recommended_next | up_next",
    "rationale": "Why the student should take or review this module",
    "recommended_item_id": "optional-uuid-of-first-incomplete-lesson-or-quiz",
    "recommended_item_title": "Lesson Title"
  }}
]
```
3. When answering general student questions, be educational, encouraging, and provide concrete examples or code snippets when explaining technical concepts.
4. Never invent fake modules or lesson IDs outside the curriculum provided above.
"""

    # 5. Build AI Message Conversation
    messages: List[AIMessage] = [AIMessage(role="system", content=system_prompt)]

    # Attach previous conversation turns (up to last 6)
    if payload.history:
        for hist in payload.history[-6:]:
            if hist.role in ("user", "assistant"):
                messages.append(AIMessage(role=hist.role, content=hist.content))

    # User message
    prompt_text = payload.message
    if payload.action == "summarize" and not payload.message:
        prompt_text = "Please provide a comprehensive summary of this course, its modules, and key learning takeaways."
    elif payload.action == "learning_path" and not payload.message:
        prompt_text = "Please evaluate my current completion and competency mastery, and give me a personalized learning path with next steps."

    messages.append(AIMessage(role="user", content=prompt_text))

    # 6. Execute LLM Call (Gemini prioritized, Groq fallback, Deterministic fallback)
    reply_text = ""
    learning_path_steps: Optional[List[LearningPathStep]] = None
    provider_used = "deterministic"
    model_used = "offline-fallback"

    try:
        ai_provider = get_ai_provider()
        req = AICompletionRequest(
            messages=messages,
            temperature=0.3,
            max_tokens=1500,
        )
        ai_resp = await ai_provider.complete(req)
        reply_text = ai_resp.content
        provider_used = ai_provider.provider_name
        model_used = ai_resp.model

        # Extract structured learning path if present
        learning_path_steps = _extract_learning_path(reply_text)
        if learning_path_steps:
            reply_text = _clean_reply_text(reply_text)

    except Exception as exc:
        logger.warning(f"Primary AI Provider failed for course chat: {exc}. Attempting Groq fallback...")
        try:
            groq_prov = get_ai_provider(provider_name="groq")
            req = AICompletionRequest(
                messages=messages,
                temperature=0.3,
                max_tokens=1500,
            )
            ai_resp = await groq_prov.complete(req)
            reply_text = ai_resp.content
            provider_used = groq_prov.provider_name
            model_used = ai_resp.model
            learning_path_steps = _extract_learning_path(reply_text)
            if learning_path_steps:
                reply_text = _clean_reply_text(reply_text)
        except Exception as groq_exc:
            logger.warning(f"Groq AI fallback also failed: {groq_exc}. Using deterministic curriculum fallback.")
            if payload.action == "summarize":
                reply_text = _generate_fallback_summary(course, sorted_modules, competencies_list)
            elif payload.action == "learning_path":
                reply_text, learning_path_steps = _generate_fallback_learning_path(
                    course, sorted_modules, progress_map, competencies_list, learner_competency_map
                )
            else:
                reply_text = (
                    f"Hello! I am your AI Course Mentor for **{course.title}**. "
                    f"You have completed **{total_completed} of {total_lessons} lessons** ({overall_progress_pct}%). "
                    f"You can ask me to summarize the course, recommend a tailored learning path, or explain any specific topic or code challenge!"
                )
            provider_used = "offline_curriculum_mentor"
            model_used = "rule-based-engine"

    # If action was learning_path but LLM didn't return valid json, generate fallback steps for UI cards
    if payload.action == "learning_path" and not learning_path_steps:
        _, learning_path_steps = _generate_fallback_learning_path(
            course, sorted_modules, progress_map, competencies_list, learner_competency_map
        )

    return CourseChatResponse(
        reply=reply_text,
        action=payload.action or "chat",
        provider=provider_used,
        model=model_used,
        learning_path=learning_path_steps,
    )
