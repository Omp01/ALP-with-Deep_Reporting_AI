"""
The quiz part of a check-in: questions written by a model from the learner's own course material, each one verified in code.

Where the material comes from: the published lessons of a course the learner is enrolled in (their text, transcript or extracted
document text, or the stored chunks). Where the questions come from: a random sample of passages, favouring passages that earlier
check-ins did not use, and a list of earlier questions to avoid, so the quiz is different every time. What stops a made-up question:
the ingestion validation, which drops any question whose quoted source passage is not actually in the material.
"""

import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestion import analysis, prompts
from app.ingestion.ai import TASK_CHECKIN, complete_structured
from app.models import Competency, ContentChunk, ContentCompetency, ContentItem, Module

CHUNK_TARGET_CHARS = 700
PASSAGES_PER_CHECKIN = 6
MIN_MATERIAL_CHARS = 300
_SPLIT = re.compile(r"\n\s*\n")


@dataclass
class Passage:
    key: str                     # "<content item id>:<n>", stable across check-ins
    item_id: UUID
    title: str
    text: str


class NotEnoughMaterial(Exception):
    """The course has no published text the quiz could be written from."""


def split_text(text: str, target: int = CHUNK_TARGET_CHARS) -> List[str]:
    """Paragraphs merged up to about `target` characters; an over-long paragraph is cut at sentence ends."""
    pieces: List[str] = []
    for para in _SPLIT.split(text or ""):
        para = " ".join(para.split())
        if not para:
            continue
        if len(para) <= target:
            pieces.append(para)
            continue
        current = ""
        for sentence in re.split(r"(?<=[.!?])\s+", para):
            if current and len(current) + len(sentence) > target:
                pieces.append(current)
                current = ""
            current = f"{current} {sentence}".strip()
        if current:
            pieces.append(current)
    merged: List[str] = []
    for piece in pieces:
        if merged and len(merged[-1]) + len(piece) + 1 <= target:
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged


async def course_passages(db: AsyncSession, org_id: UUID, course_id: UUID) -> List[Passage]:
    """Every passage of the course's published lessons, in course order."""
    items = (await db.execute(
        select(ContentItem).join(Module, Module.id == ContentItem.module_id)
        .where(ContentItem.org_id == org_id, Module.course_id == course_id, ContentItem.status == "published")
        .order_by(Module.sequence_order, ContentItem.order_index)
    )).scalars().all()
    passages: List[Passage] = []
    for item in items:
        rows = (await db.execute(select(ContentChunk).where(ContentChunk.content_item_id == item.id, ContentChunk.org_id == org_id)
                                 .order_by(ContentChunk.chunk_index))).scalars().all()
        texts = [r.text_content for r in rows if (r.text_content or "").strip()]
        if not texts:
            texts = split_text(item.raw_text or item.text_content or item.transcript or "")
        for n, text in enumerate(texts):
            if len(text.strip()) >= 40:
                passages.append(Passage(f"{item.id}:{n}", item.id, item.title, text.strip()))
    if sum(len(p.text) for p in passages) < MIN_MATERIAL_CHARS:
        raise NotEnoughMaterial("This course does not have enough published text to write a quiz from.")
    return passages


def sample_passages(passages: Sequence[Passage], used_before: Set[str], k: int, rng: random.Random) -> List[Passage]:
    """Passages nobody has been asked about recently come first; within each group the choice is random."""
    fresh = [p for p in passages if p.key not in used_before]
    stale = [p for p in passages if p.key in used_before]
    rng.shuffle(fresh)
    rng.shuffle(stale)
    return (fresh + stale)[:k]


def _prompt(title: str, excerpts: List[Tuple[int, str]], competency_names: Sequence[str], count: int, avoid: Sequence[str], nonce: str) -> str:
    earlier = "\n".join(f"- {q[:140]}" for q in avoid[:20]) or "(none)"
    names = "\n".join(f"- {n}" for n in competency_names) or "(none)"
    return (
        f"Title of the course: {prompts.defang(title)}\n"
        f"Write {count} questions. Spread them over different excerpts where you can.\n\n"
        f"COMPETENCIES (use these names in the 'competency' field):\n{names}\n\n"
        f"Questions asked in earlier check-ins (do NOT repeat or rephrase them):\n{earlier}\n\n"
        f"MATERIAL:\n{prompts.fence(excerpts, nonce)}"
    )


@dataclass
class QuizOutcome:
    questions: List[Dict[str, Any]]
    rejected: List[Dict[str, str]]
    provider: str
    model: str
    passages_used: List[str]


async def competencies_for(db: AsyncSession, org_id: UUID, item_ids: Sequence[UUID]) -> Dict[UUID, List[Tuple[UUID, str]]]:
    """content item -> [(competency id, name)] from the course's own mappings."""
    if not item_ids:
        return {}
    rows = (await db.execute(
        select(ContentCompetency.content_item_id, Competency.id, Competency.name)
        .join(Competency, Competency.id == ContentCompetency.competency_id)
        .where(ContentCompetency.content_item_id.in_(list(item_ids)), Competency.org_id == org_id)
    )).all()
    out: Dict[UUID, List[Tuple[UUID, str]]] = {}
    for item_id, comp_id, name in rows:
        out.setdefault(item_id, []).append((comp_id, name))
    return out


async def write_quiz(
    db: AsyncSession, org_id: UUID, course_title: str, passages: Sequence[Passage], avoid_questions: Sequence[str],
    used_before: Set[str], rng: random.Random,
) -> QuizOutcome:
    count = settings.checkin_question_count
    chosen = sample_passages(passages, used_before, PASSAGES_PER_CHECKIN, rng)
    chosen.sort(key=lambda p: p.key)
    # The ingestion validator locates a quote by chunk index, so each passage gets its own index in this call.
    chunks = [{"chunk_index": i, "text_content": p.text} for i, p in enumerate(chosen)]
    mapped = await competencies_for(db, org_id, list({p.item_id for p in chosen}))
    names = sorted({name for p in chosen for _, name in mapped.get(p.item_id, [])})

    nonce = prompts.new_nonce()
    result = await complete_structured(
        TASK_CHECKIN, prompts.QUESTIONS_SYSTEM,
        _prompt(course_title, [(c["chunk_index"], c["text_content"]) for c in chunks], names, count + 2, avoid_questions, nonce),
        analysis.QuestionsOut, max_tokens=4000, temperature=0.7,
    )
    accepted, rejected = analysis.validate_questions(result.value.questions, chunks, names)  # type: ignore[attr-defined]

    questions: List[Dict[str, Any]] = []
    for q in accepted[:count]:
        passage = chosen[q.chunk_index] if q.chunk_index is not None and 0 <= q.chunk_index < len(chosen) else None
        comps = mapped.get(passage.item_id, []) if passage else []
        comp = next((c for c in comps if c[1] == q.competency_name), comps[0] if len(comps) == 1 else None)
        questions.append({
            "id": f"q{len(questions) + 1}", "text": q.question_text,
            "options": [{"id": o["id"], "text": o["text"], "is_correct": bool(o["is_correct"])} for o in q.options],
            "explanation": q.explanation, "source_quote": q.source_quote, "difficulty": q.difficulty,
            "content_item_id": str(passage.item_id) if passage else None, "content_title": passage.title if passage else None,
            "passage_key": passage.key if passage else None,
            "competency_id": str(comp[0]) if comp else None, "competency_name": comp[1] if comp else q.competency_name,
        })
    return QuizOutcome(questions, rejected, result.provider, result.model, [p.key for p in chosen])
