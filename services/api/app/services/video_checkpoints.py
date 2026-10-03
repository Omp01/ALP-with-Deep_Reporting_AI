"""
Service for interactive video checkpoints, AI question generation from transcripts,
anti-skipping seek validation, and learner comprehension progress tracking.
"""

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.competency import service as competency_service
from app.models.course import ContentItem
from app.models.video_checkpoint import LearnerVideoCheckpoint, VideoCheckpoint, VideoCheckpointAttempt
from app.schemas.video_checkpoint import (
    CheckpointOption,
    CheckpointRemediation,
    VideoCheckpointAnswerResponse,
    VideoCheckpointItem,
    VideoCheckpointsResponse,
    VideoSeekValidationResponse,
)
from app.services.scoring import calculate_flashcard_score
from shared.schemas.ai_provider import (
    AICompletionRequest,
    AIMessage,
    get_ai_provider,
)


logger = logging.getLogger("api.video_checkpoints")


# ---------------------------------------------------------------------------
# Transcript & Timing Helpers
# ---------------------------------------------------------------------------

TIMESTAMP_REGEX = re.compile(
    r"(?:\[?(\d{1,2}):(\d{2})(?::(\d{2}))?\]?|(\d{1,2}):(\d{2}))"
)


def parse_timestamp_seconds(time_str: str) -> Optional[float]:
    """Converts MM:SS or HH:MM:SS to seconds."""
    parts = time_str.strip("[]() ").split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (ValueError, IndexError):
        return None
    return None


def extract_transcript_cues(transcript: str) -> List[Tuple[float, str]]:
    """
    Extracts timestamped cues from a transcript if present.
    Matches lines like:
    [01:23] Some text here
    or
    01:23 - Some text here
    """
    lines = transcript.splitlines()
    cues: List[Tuple[float, str]] = []
    line_time_pattern = re.compile(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–—:]?\s*(.*)$")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = line_time_pattern.match(line)
        if m:
            sec = parse_timestamp_seconds(m.group(1))
            text = m.group(2).strip()
            if sec is not None and text:
                cues.append((sec, text))

    return cues


def generate_fallback_checkpoints(
    transcript: str, duration_seconds: int
) -> List[Dict]:
    """
    Deterministic rule-based checkpoint generator for offline/fallback mode.
    Splits transcript into logical sections and creates grounded questions.
    """
    paragraphs = [p.strip() for p in transcript.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in transcript.split(". ") if len(p.strip()) > 30]

    if not paragraphs:
        paragraphs = [transcript[:300]]

    effective_duration = duration_seconds if duration_seconds > 60 else max(len(paragraphs) * 60, 180)
    
    # We want 2 to 4 checkpoints depending on duration
    count = min(max(2, effective_duration // 120), min(4, len(paragraphs)))
    step_time = effective_duration / (count + 1)

    generated = []
    for i in range(count):
        ts = round(step_time * (i + 1), 1)
        p_idx = min(i, len(paragraphs) - 1)
        paragraph = paragraphs[p_idx]
        
        # Pick a meaningful sentence or concept
        sentences = [s.strip() for s in re.split(r"[.!?]", paragraph) if len(s.strip()) > 20]
        chosen_sentence = sentences[0] if sentences else paragraph[:120]
        
        # Extract a short excerpt for context
        excerpt = chosen_sentence[:180]

        # Generate a question grounded in this sentence
        words = chosen_sentence.split()
        key_term = words[0] if len(words) > 0 else "This concept"
        if len(words) > 3:
            key_term = " ".join(words[:3])

        topic_name = f"{key_term.title()} Overview"
        start_ts = max(0.0, round(ts - 45.0, 1))

        question_text = f"According to the video discussed around this topic: '{excerpt[:90]}...', what is the key takeaway?"
        
        correct_answer = f"It emphasizes that {chosen_sentence[:75].lower()}"
        
        options = [
            {"id": "A", "text": correct_answer},
            {"id": "B", "text": "It completely contradicts the previous core principles."},
            {"id": "C", "text": "It is an optional practice with no measurable impact."},
            {"id": "D", "text": "It should only be applied in non-standard edge cases."},
        ]

        generated.append({
            "timestamp_seconds": ts,
            "timestamp_start_seconds": start_ts,
            "timestamp_end_seconds": ts,
            "topic": topic_name,
            "transcript_segment": excerpt,
            "question": question_text,
            "options": options,
            "correct_option_id": "A",
            "explanation": f"Based directly on the covered segment: '{excerpt}'.",
            "order_index": i + 1,
            "max_score": 10.0,
        })

    return generated


async def generate_ai_checkpoints(
    transcript: str, duration_seconds: int, title: str
) -> List[Dict]:
    """
    Uses the multi-provider LLM (Gemini Flash / Groq) to generate grounded comprehension checkpoints.
    """
    effective_duration = duration_seconds if duration_seconds > 60 else 300
    target_count = min(max(2, effective_duration // 120), 4)

    prompt = f"""You are an expert instructional designer and video learning specialist.
Analyze this video lesson transcript and generate {target_count} periodic comprehension checkpoints.

Video Title: {title}
Estimated Duration: {effective_duration} seconds

TRANSCRIPT:
\"\"\"{transcript[:6000]}\"\"\"

REQUIREMENTS:
1. Generate between 2 and {target_count} checkpoints spaced every 90 to 180 seconds along the video timeline (timestamp_seconds must be between 30 and {effective_duration - 15}).
2. Provide timestamp_start_seconds (where this concept was introduced, ~30-60s prior) and timestamp_end_seconds (timestamp_seconds).
3. Provide a concise topic/concept name (e.g. 'Decorator Wrapper Functions', 'Token Expiration').
4. Each question MUST be strictly grounded in the transcript text covered immediately before that timestamp.
5. Questions should test genuine active understanding and attention, NOT trivial word matching.
6. Each question must have exactly 4 plausible multiple-choice options (A, B, C, D). Only ONE must be unambiguously correct.
7. Provide a clear, concise explanation referencing what the video explained.
8. Provide the exact excerpt from the transcript that supports the answer.

Respond ONLY with a valid JSON array in this exact format:
[
  {{
    "timestamp_seconds": 120.0,
    "timestamp_start_seconds": 90.0,
    "timestamp_end_seconds": 120.0,
    "topic": "Python Decorators Syntax",
    "transcript_segment": "Exact short quote from transcript around this point",
    "question": "Clear comprehension question?",
    "options": [
      {{"id": "A", "text": "Option A text"}},
      {{"id": "B", "text": "Option B text"}},
      {{"id": "C", "text": "Option C text"}},
      {{"id": "D", "text": "Option D text"}}
    ],
    "correct_option_id": "A",
    "explanation": "Why A is correct based on the transcript",
    "order_index": 1,
    "max_score": 10.0
  }}
]
"""
    try:
        ai_provider = get_ai_provider()
        req = AICompletionRequest(
            messages=[
                AIMessage(role="system", content="You are a JSON-only response generator for instructional video checkpoints."),
                AIMessage(role="user", content=prompt),
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        resp = await ai_provider.complete(req)
        content = resp.content.strip()

        # Extract JSON array
        json_match = re.search(r"\[\s*\{.*\}\s*\]", content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list) and len(parsed) > 0:
                validated = []
                for idx, item in enumerate(parsed):
                    ts = float(item.get("timestamp_seconds", (idx + 1) * 90))
                    start_ts = float(item.get("timestamp_start_seconds", max(0.0, ts - 45.0)))
                    end_ts = float(item.get("timestamp_end_seconds", ts))
                    topic_str = str(item.get("topic", f"Topic Checkpoint {idx + 1}"))
                    validated.append({
                        "timestamp_seconds": ts,
                        "timestamp_start_seconds": start_ts,
                        "timestamp_end_seconds": end_ts,
                        "topic": topic_str,
                        "transcript_segment": str(item.get("transcript_segment", "")),
                        "question": str(item.get("question", "")),
                        "options": item.get("options", []),
                        "correct_option_id": str(item.get("correct_option_id", "A")).upper(),
                        "explanation": str(item.get("explanation", "")),
                        "order_index": idx + 1,
                        "max_score": float(item.get("max_score", 10.0)),
                    })
                return sorted(validated, key=lambda x: x["timestamp_seconds"])

    except Exception as exc:
        logger.warning(f"AI checkpoint generation failed, falling back to rule-based: {exc}")

    return generate_fallback_checkpoints(transcript, duration_seconds)



# ---------------------------------------------------------------------------
# Database Service Functions
# ---------------------------------------------------------------------------

async def get_or_create_checkpoints_for_content(
    db: AsyncSession,
    org_id: UUID,
    content_item_id: UUID,
    user_id: UUID,
    force_regenerate: bool = False,
) -> VideoCheckpointsResponse:
    """
    Fetches all checkpoints for a video content item, generating them if they don't exist,
    and attaches the learner's completion status.
    """
    # 1. Fetch existing checkpoints
    chk_query = (
        select(VideoCheckpoint)
        .where(
            and_(
                VideoCheckpoint.content_item_id == content_item_id,
                VideoCheckpoint.org_id == org_id,
            )
        )
        .order_index_asc() if hasattr(select(VideoCheckpoint), "order_index_asc") else
        select(VideoCheckpoint)
        .where(
            and_(
                VideoCheckpoint.content_item_id == content_item_id,
                VideoCheckpoint.org_id == org_id,
            )
        )
        .order_by(VideoCheckpoint.timestamp_seconds.asc())
    )
    result = await db.execute(chk_query)
    existing_checkpoints = list(result.scalars().all())

    # 2. If no checkpoints or force_regenerate is requested, generate them
    if not existing_checkpoints or force_regenerate:
        # Fetch content item
        ci_res = await db.execute(
            select(ContentItem).where(
                and_(ContentItem.id == content_item_id, ContentItem.org_id == org_id)
            )
        )
        item = ci_res.scalar_one_or_none()
        if item is not None:
            transcript_text = item.transcript or item.text_content or item.raw_text or ""
            if not transcript_text and item.analysis:
                # Synthesize text from analysis if available
                topics = item.analysis.get("key_topics", [])
                objectives = item.analysis.get("learning_objectives", [])
                transcript_text = f"Key topics: {', '.join(topics)}. Learning objectives: {', '.join(objectives)}."

            if transcript_text:
                if force_regenerate and existing_checkpoints:
                    for old_chk in existing_checkpoints:
                        await db.delete(old_chk)
                    await db.flush()

                raw_checkpoints = await generate_ai_checkpoints(
                    transcript=transcript_text,
                    duration_seconds=item.duration_seconds or 300,
                    title=item.title,
                )

                created_checkpoints = []
                for chk_data in raw_checkpoints:
                    chk = VideoCheckpoint(
                        org_id=org_id,
                        content_item_id=content_item_id,
                        timestamp_seconds=chk_data["timestamp_seconds"],
                        timestamp_start_seconds=chk_data.get("timestamp_start_seconds"),
                        timestamp_end_seconds=chk_data.get("timestamp_end_seconds"),
                        topic=chk_data.get("topic"),
                        transcript_segment=chk_data.get("transcript_segment"),
                        question=chk_data["question"],
                        options=chk_data["options"],
                        correct_option_id=chk_data["correct_option_id"],
                        explanation=chk_data.get("explanation"),
                        order_index=chk_data.get("order_index", 0),
                        max_score=chk_data.get("max_score", 10.0),
                    )
                    db.add(chk)
                    created_checkpoints.append(chk)

                await db.commit()
                # Reload ordered
                res = await db.execute(
                    select(VideoCheckpoint)
                    .where(
                        and_(
                            VideoCheckpoint.content_item_id == content_item_id,
                            VideoCheckpoint.org_id == org_id,
                        )
                    )
                    .order_by(VideoCheckpoint.timestamp_seconds.asc())
                )
                existing_checkpoints = list(res.scalars().all())

    # 3. Load learner responses
    learner_map: Dict[UUID, LearnerVideoCheckpoint] = {}
    if existing_checkpoints:
        chk_ids = [c.id for c in existing_checkpoints]
        l_res = await db.execute(
            select(LearnerVideoCheckpoint).where(
                and_(
                    LearnerVideoCheckpoint.user_id == user_id,
                    LearnerVideoCheckpoint.checkpoint_id.in_(chk_ids),
                )
            )
        )
        for l_chk in l_res.scalars().all():
            learner_map[l_chk.checkpoint_id] = l_chk

    # 4. Build response items
    items: List[VideoCheckpointItem] = []
    completed_count = 0

    for chk in existing_checkpoints:
        l_record = learner_map.get(chk.id)
        status = l_record.status if l_record else "pending"
        selected_option = l_record.selected_option_id if l_record else None
        attempts = l_record.attempt_count if l_record else 0

        is_answered = status in ("correct", "incorrect", "answered")
        if status in ("correct", "answered"):
            completed_count += 1

        options = [CheckpointOption(id=opt["id"], text=opt["text"]) for opt in chk.options]

        items.append(
            VideoCheckpointItem(
                id=chk.id,
                content_item_id=chk.content_item_id,
                timestamp_seconds=chk.timestamp_seconds,
                timestamp_start_seconds=chk.timestamp_start_seconds,
                timestamp_end_seconds=chk.timestamp_end_seconds,
                topic=chk.topic,
                transcript_segment=chk.transcript_segment,
                question=chk.question,
                options=options,
                order_index=chk.order_index,
                max_score=chk.max_score or 10.0,
                status=status,
                selected_option_id=selected_option,
                attempt_count=attempts,
                score=l_record.score if l_record else 0.0,
                formula_id=l_record.formula_id if l_record else None,
                calculation_details=l_record.calculation_details if l_record else None,
                # Hide answer & explanation until attempted to prevent cheating via inspect element
                correct_option_id=chk.correct_option_id if is_answered else None,
                explanation=chk.explanation if is_answered else None,
            )
        )

    return VideoCheckpointsResponse(
        content_item_id=content_item_id,
        total_checkpoints=len(items),
        completed_checkpoints=completed_count,
        checkpoints=items,
    )


async def record_checkpoint_answer(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    content_item_id: UUID,
    checkpoint_id: UUID,
    selected_option_id: str,
) -> VideoCheckpointAnswerResponse:
    """
    Submits a learner's choice for a video checkpoint, updates learner status,
    records immutable attempt audit logs, applies attempt-decay scoring,
    and returns immediate feedback and video remediation cues.
    """
    # 1. Fetch checkpoint
    res = await db.execute(
        select(VideoCheckpoint).where(
            and_(
                VideoCheckpoint.id == checkpoint_id,
                VideoCheckpoint.content_item_id == content_item_id,
                VideoCheckpoint.org_id == org_id,
            )
        )
    )
    checkpoint = res.scalar_one_or_none()
    if not checkpoint:
        raise ValueError("Checkpoint not found")

    # Fetch ContentItem for video title
    ci_res = await db.execute(
        select(ContentItem).where(
            and_(ContentItem.id == content_item_id, ContentItem.org_id == org_id)
        )
    )
    content_item = ci_res.scalar_one_or_none()
    video_title = content_item.title if content_item else "Video Lesson"

    # 2. Evaluate answer
    clean_selection = selected_option_id.strip().upper()
    is_correct = clean_selection == checkpoint.correct_option_id.strip().upper()
    new_status = "correct" if is_correct else "incorrect"

    # 3. Determine attempt number and compute attempt-decay score
    l_res = await db.execute(
        select(LearnerVideoCheckpoint).where(
            and_(
                LearnerVideoCheckpoint.user_id == user_id,
                LearnerVideoCheckpoint.checkpoint_id == checkpoint_id,
            )
        )
    )
    learner_record = l_res.scalar_one_or_none()
    current_attempt = (learner_record.attempt_count + 1) if learner_record else 1
    max_score = float(checkpoint.max_score or 10.0)

    score_breakdown = calculate_flashcard_score(
        max_marks=max_score,
        attempt_number=current_attempt,
        is_correct=is_correct,
        penalty_p=0.25,
    )

    # 4. Insert immutable audit log for this attempt
    attempt_audit = VideoCheckpointAttempt(
        org_id=org_id,
        user_id=user_id,
        checkpoint_id=checkpoint_id,
        attempt_number=current_attempt,
        selected_option_id=clean_selection,
        is_correct=is_correct,
        score_awarded=score_breakdown.score,
        max_score=max_score,
        formula_id=score_breakdown.formula_id,
        formula_version=score_breakdown.formula_version,
        calculation_snapshot=score_breakdown.raw_details,
        created_at=datetime.utcnow(),
    )
    db.add(attempt_audit)

    # 5. Upsert LearnerVideoCheckpoint
    if not learner_record:
        learner_record = LearnerVideoCheckpoint(
            org_id=org_id,
            user_id=user_id,
            content_item_id=content_item_id,
            checkpoint_id=checkpoint_id,
            status=new_status,
            selected_option_id=clean_selection,
            attempt_count=current_attempt,
            score=score_breakdown.score,
            max_score=max_score,
            attempt_factor=score_breakdown.attempt_factor,
            accuracy_factor=score_breakdown.accuracy_factor,
            formula_id=score_breakdown.formula_id,
            formula_version=score_breakdown.formula_version,
            calculation_details=score_breakdown.raw_details,
            answered_at=datetime.utcnow(),
        )
        db.add(learner_record)
    else:
        # Preserve highest awarded score if learner was already correct
        if learner_record.status == "correct" and not is_correct:
            learner_record.attempt_count = current_attempt
            learner_record.answered_at = datetime.utcnow()
        else:
            learner_record.status = new_status
            learner_record.selected_option_id = clean_selection
            learner_record.attempt_count = current_attempt
            learner_record.score = max(learner_record.score or 0.0, score_breakdown.score)
            learner_record.max_score = max_score
            learner_record.attempt_factor = score_breakdown.attempt_factor
            learner_record.accuracy_factor = score_breakdown.accuracy_factor
            learner_record.formula_id = score_breakdown.formula_id
            learner_record.formula_version = score_breakdown.formula_version
            learner_record.calculation_details = score_breakdown.raw_details
            learner_record.answered_at = datetime.utcnow()

    # 6. Emit Competency Evidence for BKT mastery tracking if linked to a competency
    if checkpoint.competency_id:
        try:
            ev_input = competency_service.EvidenceInput(
                org_id=org_id,
                user_id=user_id,
                competency_id=checkpoint.competency_id,
                source_type="question_answered",
                signal=score_breakdown.score / max(1.0, max_score),
                attempt_number=current_attempt,
            )
            await competency_service.apply(db, ev_input)
        except Exception as ev_err:
            logger.warning(f"Could not apply competency evidence for checkpoint: {ev_err}")

    await db.commit()

    # 7. Check if all checkpoints are now completed
    total_q = await db.execute(
        select(VideoCheckpoint.id).where(
            and_(
                VideoCheckpoint.content_item_id == content_item_id,
                VideoCheckpoint.org_id == org_id,
            )
        )
    )
    all_chk_ids = [r[0] for r in total_q.all()]

    comp_q = await db.execute(
        select(LearnerVideoCheckpoint.checkpoint_id).where(
            and_(
                LearnerVideoCheckpoint.user_id == user_id,
                LearnerVideoCheckpoint.content_item_id == content_item_id,
                LearnerVideoCheckpoint.status.in_(["correct", "answered"]),
            )
        )
    )
    completed_ids = set(r[0] for r in comp_q.all())
    all_done = len(all_chk_ids) > 0 and all(cid in completed_ids for cid in all_chk_ids)

    # 8. Build video-traceable remediation metadata
    start_sec = checkpoint.timestamp_start_seconds if checkpoint.timestamp_start_seconds is not None else max(0.0, checkpoint.timestamp_seconds - 45.0)
    end_sec = checkpoint.timestamp_end_seconds if checkpoint.timestamp_end_seconds is not None else checkpoint.timestamp_seconds
    start_fmt = f"{int(start_sec // 60):02d}:{int(start_sec % 60):02d}"
    end_fmt = f"{int(end_sec // 60):02d}:{int(end_sec % 60):02d}"
    section_label = f"{start_fmt} - {end_fmt}"

    remediation = CheckpointRemediation(
        topic=checkpoint.topic or "Topic Concept",
        video_title=video_title,
        content_item_id=content_item_id,
        timestamp_start_seconds=start_sec,
        timestamp_end_seconds=end_sec,
        section_label=section_label,
        explanation=checkpoint.explanation,
        action_url=f"/learner/learning?item_id={content_item_id}&start={int(start_sec)}",
    )

    return VideoCheckpointAnswerResponse(
        checkpoint_id=checkpoint_id,
        is_correct=is_correct,
        status=new_status,
        selected_option_id=clean_selection,
        correct_option_id=checkpoint.correct_option_id,
        score=score_breakdown.score,
        max_score=max_score,
        attempt_number=current_attempt,
        formula_id=score_breakdown.formula_id,
        formula_version=score_breakdown.formula_version,
        calculation_details=score_breakdown.raw_details,
        reason=score_breakdown.reason,
        remediation=remediation,
        explanation=checkpoint.explanation,
        all_checkpoints_completed=all_done,
    )


async def update_checkpoint_status(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    content_item_id: UUID,
    checkpoint_id: UUID,
    status: str,
) -> None:
    """
    Marks checkpoint status e.g. 'displayed' when the popup appears.
    """
    res = await db.execute(
        select(LearnerVideoCheckpoint).where(
            and_(
                LearnerVideoCheckpoint.user_id == user_id,
                LearnerVideoCheckpoint.checkpoint_id == checkpoint_id,
            )
        )
    )
    record = res.scalar_one_or_none()
    if not record:
        record = LearnerVideoCheckpoint(
            org_id=org_id,
            user_id=user_id,
            content_item_id=content_item_id,
            checkpoint_id=checkpoint_id,
            status=status,
            attempt_count=0,
        )
        db.add(record)
    else:
        # Don't downgrade answered or correct to displayed
        if record.status not in ("correct", "answered"):
            record.status = status

    await db.commit()


async def validate_seek(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    content_item_id: UUID,
    current_time: float,
    target_time: float,
) -> VideoSeekValidationResponse:
    """
    Validates seeking from current_time to target_time.
    If target_time > current_time, ensures all intermediate checkpoints are completed.
    Seeking backward (target_time <= current_time) is always permitted.
    """
    # Seeking backward or staying in place is always allowed
    if target_time <= current_time:
        return VideoSeekValidationResponse(allowed=True)

    # Fetch checkpoints between current_time and target_time
    checkpoints_res = await db.execute(
        select(VideoCheckpoint)
        .where(
            and_(
                VideoCheckpoint.content_item_id == content_item_id,
                VideoCheckpoint.org_id == org_id,
                VideoCheckpoint.timestamp_seconds > current_time,
                VideoCheckpoint.timestamp_seconds <= target_time,
            )
        )
        .order_by(VideoCheckpoint.timestamp_seconds.asc())
    )
    intermediate_checkpoints = list(checkpoints_res.scalars().all())

    if not intermediate_checkpoints:
        return VideoSeekValidationResponse(allowed=True)

    # Check learner status for these checkpoints
    chk_ids = [c.id for c in intermediate_checkpoints]
    l_res = await db.execute(
        select(LearnerVideoCheckpoint).where(
            and_(
                LearnerVideoCheckpoint.user_id == user_id,
                LearnerVideoCheckpoint.checkpoint_id.in_(chk_ids),
            )
        )
    )
    completed_ids = set()
    for l_chk in l_res.scalars().all():
        if l_chk.status in ("correct", "answered"):
            completed_ids.add(l_chk.checkpoint_id)

    # Find missed checkpoints
    missed: List[VideoCheckpointItem] = []
    for c in intermediate_checkpoints:
        if c.id not in completed_ids:
            options = [CheckpointOption(id=opt["id"], text=opt["text"]) for opt in c.options]
            missed.append(
                VideoCheckpointItem(
                    id=c.id,
                    content_item_id=c.content_item_id,
                    timestamp_seconds=c.timestamp_seconds,
                    transcript_segment=c.transcript_segment,
                    question=c.question,
                    options=options,
                    order_index=c.order_index,
                    status="pending",
                )
            )

    if missed:
        return VideoSeekValidationResponse(
            allowed=False,
            reason=f"Cannot skip forward: {len(missed)} checkpoint(s) must be completed first.",
            first_missed_checkpoint=missed[0],
            missed_checkpoints=missed,
        )

    return VideoSeekValidationResponse(allowed=True)
