"""
Content analysis and question generation.

The model proposes; this module verifies. Nothing the model says reaches the database
without passing the checks below.

  * Analysis (objectives, concepts, competencies) is parsed into strict schemas.
  * Competencies are matched against the tenant's EXISTING skills so the platform reuses
    "SQL Joins" instead of accumulating "SQL JOIN Operations", "Joining tables in SQL"...
  * A generated question is accepted only if:
      - it is well-formed multiple choice (3-5 distinct options, one correct);
      - its source quote appears VERBATIM in the material (checked here, in code);
      - it is not a near-duplicate of one already accepted.
    A question that fails any check is dropped and the reason recorded; it is never
    repaired or invented.
"""

import hashlib
import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.ingestion import prompts
from app.ingestion.ai import TASK_ANALYSIS, TASK_QUESTIONS, complete_structured
from app.ingestion.errors import EmptyContent

BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]
Level = Literal["beginner", "intermediate", "advanced"]

NEAR_DUPLICATE_RATIO = 0.85
COMPETENCY_MATCH_THRESHOLD = 0.85
MIN_QUOTE_CHARS = 20
BANNED_OPTIONS = re.compile(r"\b(all|none) of the above\b", re.IGNORECASE)
STOPWORDS = {"a", "an", "the", "of", "and", "in", "to", "for", "with", "on", "basics", "fundamentals", "introduction", "intro"}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unit_interval(value: Any, default: float = 0.5) -> float:
    """Models often answer difficulty as 1-10 or as text; coerce to 0..1 or fall back."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number > 1.0:
        number = number / 10.0 if number <= 10 else 1.0
    return min(max(number, 0.0), 1.0)


# ------------------------------------------------------------------------------ schemas
class ConceptOut(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    explanation: str = Field("", max_length=500)

    @field_validator("name", "explanation", mode="before")
    @classmethod
    def _tidy(cls, value):
        return _clean(value)


class CompetencyOut(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field("", max_length=500)
    domain: Optional[str] = Field(None, max_length=60)
    bloom_level: BloomLevel = "understand"
    difficulty: float = 0.5
    existing_code: Optional[str] = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def _tidy(cls, value):
        return _clean(value)

    @field_validator("difficulty", mode="before")
    @classmethod
    def _difficulty(cls, value):
        return _unit_interval(value)

    @field_validator("bloom_level", mode="before")
    @classmethod
    def _bloom(cls, value):
        text = _clean(value).lower()
        return text if text in ("remember", "understand", "apply", "analyze", "evaluate", "create") else "understand"

    @field_validator("domain", mode="before")
    @classmethod
    def _domain(cls, value):
        text = re.sub(r"[^a-z0-9]+", "-", _clean(value).lower()).strip("-")
        return text or None

    @field_validator("existing_code", mode="before")
    @classmethod
    def _code(cls, value):
        text = _clean(value)
        return None if text.lower() in ("", "null", "none") else text


class AnalysisOut(BaseModel):
    summary: str = Field(..., min_length=20, max_length=1000)
    level: Level = "intermediate"
    objectives: List[str] = Field(..., min_length=2, max_length=10)
    concepts: List[ConceptOut] = Field(default_factory=list, max_length=15)
    competencies: List[CompetencyOut] = Field(..., min_length=1, max_length=5)

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, value):
        return _clean(value)

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value):
        text = _clean(value).lower()
        return text if text in ("beginner", "intermediate", "advanced") else "intermediate"

    @field_validator("objectives", mode="before")
    @classmethod
    def _objectives(cls, value):
        seen, result = set(), []
        for item in value or []:
            text = _clean(item)
            if 10 <= len(text) <= 300 and text.lower() not in seen:
                seen.add(text.lower())
                result.append(text)
        return result


class QuestionOut(BaseModel):
    question: str
    options: List[str]
    correct_index: int
    explanation: str = ""
    difficulty: float = 0.5
    competency: str = ""
    source_quote: str = ""
    chunk_index: Optional[int] = None

    @field_validator("options", mode="before")
    @classmethod
    def _options(cls, value):
        """Accept ["a", "b"] or [{"text": "a"}, ...]."""
        if not isinstance(value, list):
            return value
        return [o.get("text") or o.get("option") or "" if isinstance(o, dict) else o for o in value]

    @field_validator("correct_index", mode="before")
    @classmethod
    def _correct(cls, value):
        """Accept 1, "1", or a letter like "B"."""
        if isinstance(value, str):
            text = value.strip().lower()
            if len(text) == 1 and text.isalpha():
                return ord(text) - 97
            if text.isdigit():
                return int(text)
        return value

    @field_validator("difficulty", mode="before")
    @classmethod
    def _difficulty(cls, value):
        return _unit_interval(value)

    @field_validator("chunk_index", mode="before")
    @classmethod
    def _chunk(cls, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class QuestionsOut(BaseModel):
    questions: List[QuestionOut] = Field(..., min_length=1, max_length=20)


# ----------------------------------------------------------------------- text utilities
def compact(text: str) -> str:
    """Lower-case letters and digits only: robust to spacing, punctuation and markdown differences."""
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", text or "").lower())


def quote_is_in(quote: str, source: str) -> bool:
    needle = compact(quote)
    return len(needle) >= MIN_QUOTE_CHARS and needle in compact(source)


def select_excerpts(chunks: Sequence[Dict[str, Any]], max_chars: int) -> List[Tuple[int, str]]:
    """The whole document if it fits, otherwise chunks spread evenly across it (start, middle and end all represented)."""
    total = sum(len(c["text_content"]) for c in chunks)
    if total <= max_chars:
        return [(c["chunk_index"], c["text_content"]) for c in chunks]
    average = max(1, total // len(chunks))
    wanted = max(1, min(len(chunks), max_chars // average))
    if wanted == 1:
        picks = [0]
    else:
        picks = sorted({round(i * (len(chunks) - 1) / (wanted - 1)) for i in range(wanted)})
    return [(chunks[i]["chunk_index"], chunks[i]["text_content"]) for i in picks]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "skill"


# ------------------------------------------------------------- competency resolution
@dataclass(frozen=True)
class ExistingCompetency:
    id: str
    code: str
    name: str


def _name_tokens(name: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in STOPWORDS}


def name_similarity(a: str, b: str) -> float:
    ta, tb = _name_tokens(a), _name_tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    ratio = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio() if ta and tb else 0.0
    return max(jaccard, ratio)


def resolve_competencies(proposed: Sequence[CompetencyOut], existing: Sequence[ExistingCompetency]) -> List[Dict[str, Any]]:
    """
    Decide, for each proposed competency, whether it IS an existing one (link) or is new (create).

    A match needs either the model naming an existing code that really exists, or a name
    similarity of at least COMPETENCY_MATCH_THRESHOLD. The administrator can change any decision.
    """
    by_code = {e.code.lower(): e for e in existing}
    taken_codes = set(by_code)
    used_existing: set = set()
    resolved: List[Dict[str, Any]] = []

    for item in proposed:
        match: Optional[ExistingCompetency] = None
        score = 0.0
        if item.existing_code and item.existing_code.lower() in by_code:
            match, score = by_code[item.existing_code.lower()], 1.0
        else:
            for candidate in existing:
                similarity = name_similarity(item.name, candidate.name)
                if similarity > score:
                    match, score = candidate, similarity
            if score < COMPETENCY_MATCH_THRESHOLD:
                match = None

        if match is not None and match.id in used_existing:
            continue  # two proposals collapsed onto the same existing skill
        if match is not None:
            used_existing.add(match.id)
            resolved.append({
                "name": match.name, "description": item.description, "domain": item.domain,
                "bloom_level": item.bloom_level, "difficulty": item.difficulty,
                "action": "link", "competency_id": match.id, "code": match.code, "match_score": round(score, 3),
            })
            continue

        base = f"{item.domain or 'general'}.{slug(item.name)}"
        code, n = base, 2
        while code.lower() in taken_codes:
            code, n = f"{base}-{n}", n + 1
        taken_codes.add(code.lower())
        resolved.append({
            "name": item.name, "description": item.description, "domain": item.domain,
            "bloom_level": item.bloom_level, "difficulty": item.difficulty,
            "action": "create", "competency_id": None, "code": code, "match_score": round(score, 3) if score else None,
        })
    return resolved


# ----------------------------------------------------------------------------- analysis
@dataclass
class AnalysisOutcome:
    analysis: Dict[str, Any]
    provider: str
    model: str


async def analyze_content(
    title: str, chunks: Sequence[Dict[str, Any]], existing: Sequence[ExistingCompetency], input_hash: str
) -> AnalysisOutcome:
    if not chunks:
        raise EmptyContent("There is no text to analyse.")
    excerpts = select_excerpts(chunks, settings.ingestion_max_analysis_chars)
    nonce = prompts.new_nonce()
    result = await complete_structured(
        TASK_ANALYSIS,
        prompts.ANALYSIS_SYSTEM,
        prompts.analysis_prompt(title, excerpts, [(e.code, e.name) for e in existing], nonce),
        AnalysisOut,
    )
    out: AnalysisOut = result.value  # type: ignore[assignment]
    analysis = {
        "version": 1,
        "prompt_version": prompts.PROMPT_VERSION,
        "input_hash": input_hash,
        "summary": out.summary,
        "level": out.level,
        "objectives": out.objectives,
        "concepts": [c.model_dump() for c in out.concepts],
        "competencies": resolve_competencies(out.competencies, existing),
        "excerpt_chunks": [index for index, _ in excerpts],
        "provenance": {
            "provider": result.provider, "model": result.model, "attempts": result.attempts,
            "generated_at": datetime.utcnow().isoformat(),
        },
        "edited": False,
    }
    return AnalysisOutcome(analysis, result.provider, result.model)


# ---------------------------------------------------------------------------- questions
@dataclass
class ValidQuestion:
    question_text: str
    options: List[Dict[str, Any]]
    explanation: str
    difficulty: float
    competency_name: Optional[str]
    source_quote: str
    chunk_index: Optional[int]


def _shuffled(question: str, options: List[str], correct_index: int) -> Tuple[List[str], int]:
    """Models put the right answer first far too often. A seed derived from the question keeps this reproducible."""
    order = list(range(len(options)))
    random.Random(hashlib.sha256(question.encode()).hexdigest()).shuffle(order)
    return [options[i] for i in order], order.index(correct_index)


def validate_questions(
    raw: Sequence[QuestionOut],
    chunks: Sequence[Dict[str, Any]],
    competency_names: Sequence[str],
) -> Tuple[List[ValidQuestion], List[Dict[str, str]]]:
    """Keep only questions that pass every check; report why each of the others was dropped."""
    source = " ".join(c["text_content"] for c in chunks)
    accepted: List[ValidQuestion] = []
    rejected: List[Dict[str, str]] = []

    def reject(item: QuestionOut, reason: str) -> None:
        rejected.append({"question": _clean(item.question)[:160], "reason": reason})

    for item in raw:
        text = _clean(item.question)
        options = [_clean(o) for o in item.options]
        if not 10 <= len(text) <= 500:
            reject(item, "question text has an unusable length")
            continue
        if not 3 <= len(options) <= 5 or any(not o or len(o) > 250 for o in options):
            reject(item, "needs 3-5 non-empty options")
            continue
        if len({o.lower() for o in options}) != len(options):
            reject(item, "options are not distinct")
            continue
        if any(BANNED_OPTIONS.search(o) for o in options):
            reject(item, "uses 'all/none of the above'")
            continue
        if not 0 <= item.correct_index < len(options):
            reject(item, "correct_index does not point at an option")
            continue
        if not quote_is_in(item.source_quote, source):
            reject(item, "source quote is not in the material")
            continue
        if any(SequenceMatcher(None, text.lower(), q.question_text.lower()).ratio() > NEAR_DUPLICATE_RATIO for q in accepted):
            reject(item, "near-duplicate of another question")
            continue

        chunk_index = item.chunk_index
        located = next((c["chunk_index"] for c in chunks if quote_is_in(item.source_quote, c["text_content"])), None)
        if located is not None:
            chunk_index = located  # trust where the quote actually is, not where the model said

        shuffled, correct = _shuffled(text, options, item.correct_index)
        competency = next(
            (n for n in competency_names if name_similarity(item.competency, n) >= COMPETENCY_MATCH_THRESHOLD), None
        )
        accepted.append(ValidQuestion(
            question_text=text,
            options=[{"id": chr(97 + i), "text": o, "is_correct": i == correct} for i, o in enumerate(shuffled)],
            explanation=_clean(item.explanation),
            difficulty=item.difficulty,
            competency_name=competency,
            source_quote=_clean(item.source_quote),
            chunk_index=chunk_index,
        ))
    return accepted, rejected


@dataclass
class QuestionOutcome:
    accepted: List[ValidQuestion]
    rejected: List[Dict[str, str]]
    provider: str
    model: str


async def generate_questions(
    title: str, chunks: Sequence[Dict[str, Any]], competency_names: Sequence[str], count: Optional[int] = None
) -> QuestionOutcome:
    count = count or settings.ingestion_question_count
    excerpts = select_excerpts(chunks, settings.ingestion_max_analysis_chars)
    nonce = prompts.new_nonce()
    result = await complete_structured(
        TASK_QUESTIONS,
        prompts.QUESTIONS_SYSTEM,
        prompts.questions_prompt(title, excerpts, list(competency_names), count, nonce),
        QuestionsOut,
        max_tokens=4000,
    )
    out: QuestionsOut = result.value  # type: ignore[assignment]
    accepted, rejected = validate_questions(out.questions, chunks, competency_names)
    return QuestionOutcome(accepted, rejected, result.provider, result.model)
