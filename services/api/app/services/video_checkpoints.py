"""
Service for interactive video checkpoints, AI question generation from transcripts,
anti-skipping seek validation, and learner comprehension progress tracking.
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import ContentItem
from app.models.video_checkpoint import LearnerVideoCheckpoint, VideoCheckpoint
from app.schemas.video_checkpoint import (
    CheckpointOption,
    VideoCheckpointAnswerResponse,
    VideoCheckpointItem,
    VideoCheckpointsResponse,
    VideoSeekValidationResponse,
)
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
            "transcript_segment": excerpt,
            "question": question_text,
            "options": options,
            "correct_option_id": "A",
            "explanation": f"Based directly on the covered segment: '{excerpt}'.",
            "order_index": i + 1,
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
2. Each question MUST be strictly grounded in the transcript text covered immediately before that timestamp.
3. Questions should test genuine active understanding and attention (e.g. concepts, definitions, relationships, rationale), NOT trivial word matching.
4. Each question must have exactly 4 plausible multiple-choice options (A, B, C, D). Only ONE must be unambiguously correct according to the transcript.
5. Provide a clear, concise explanation referencing what the video explained.
6. Provide the exact excerpt from the transcript that supports the answer.

Respond ONLY with a valid JSON array in this exact format:
[
  {{
    "timestamp_seconds": 120.0,
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
    "order_index": 1
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
                    validated.append({
                        "timestamp_seconds": ts,
                        "transcript_segment": str(item.get("transcript_segment", "")),
                        "question": str(item.get("question", "")),
                        "options": item.get("options", []),
                        "correct_option_id": str(item.get("correct_option_id", "A")).upper(),
                        "explanation": str(item.get("explanation", "")),
                        "order_index": idx + 1,
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
                        transcript_segment=chk_data.get("transcript_segment"),
                        question=chk_data["question"],
                        options=chk_data["options"],
                        correct_option_id=chk_data["correct_option_id"],
                        explanation=chk_data.get("explanation"),
                        order_index=chk_data.get("order_index", 0),
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
                transcript_segment=chk.transcript_segment,
                question=chk.question,
                options=options,
                order_index=chk.order_index,
                status=status,
                selected_option_id=selected_option,
                attempt_count=attempts,
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
    and returns immediate feedback.
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

    # 2. Evaluate answer
    clean_selection = selected_option_id.strip().upper()
    is_correct = clean_selection == checkpoint.correct_option_id.strip().upper()
    new_status = "correct" if is_correct else "incorrect"

    # 3. Upsert LearnerVideoCheckpoint
    l_res = await db.execute(
        select(LearnerVideoCheckpoint).where(
            and_(
                LearnerVideoCheckpoint.user_id == user_id,
                LearnerVideoCheckpoint.checkpoint_id == checkpoint_id,
            )
        )
    )
    learner_record = l_res.scalar_one_or_none()
    if not learner_record:
        learner_record = LearnerVideoCheckpoint(
            org_id=org_id,
            user_id=user_id,
            content_item_id=content_item_id,
            checkpoint_id=checkpoint_id,
            status=new_status,
            selected_option_id=clean_selection,
            attempt_count=1,
            answered_at=datetime.utcnow(),
        )
        db.add(learner_record)
    else:
        learner_record.status = new_status
        learner_record.selected_option_id = clean_selection
        learner_record.attempt_count += 1
        learner_record.answered_at = datetime.utcnow()

    await db.commit()

    # 4. Check if all checkpoints are now completed
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

    return VideoCheckpointAnswerResponse(
        checkpoint_id=checkpoint_id,
        is_correct=is_correct,
        status=new_status,
        selected_option_id=clean_selection,
        correct_option_id=checkpoint.correct_option_id,
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
