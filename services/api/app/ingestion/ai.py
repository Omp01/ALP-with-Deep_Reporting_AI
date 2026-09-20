"""
AI access for the ingestion pipeline.

The pipeline depends on the `AIProvider` interface (shared/schemas/ai_provider.py), never
on a vendor. This module decides WHICH provider and model to use for a task from settings,
and gives tests a single override point.

    AI_PROVIDER=ollama              local model, free, no key
    AI_PROVIDER=gemini | groq       external (needs a key)
    AI_PROVIDER=openai_compatible   any OpenAI-compatible endpoint (vLLM, LM Studio, OpenAI...)
    AI_PROVIDER=none                AI stages are reported as unavailable, never faked

If nothing usable is configured, `provider_for` raises AIUnavailable. The pipeline records
that on the job; it does not substitute made-up output.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.ingestion.errors import AIOutputInvalid, AIUnavailable
from shared.schemas.ai_provider import (
    AICompletionRequest,
    AIMessage,
    AIProvider,
    AIProviderError,
    GeminiProvider,
    GroqProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
)

T = TypeVar("T", bound=BaseModel)

TASK_ANALYSIS = "analysis"
TASK_QUESTIONS = "questions"
TASK_GRADING = "grading"
TASK_REPORTING = "reporting"

# Tests (and only tests) replace how providers are built.
_factory_override: Optional[Callable[[str], AIProvider]] = None


def brief(error: Exception) -> str:
    """A provider error without the request URL or the HTTP library's documentation link, for showing to an admin."""
    message = re.sub(r"\s*for url '[^']*'", "", str(error))
    message = re.sub(r"\s*For more information check:.*", "", message, flags=re.S)
    message = re.sub(r"^AI provider failed( after \d+ attempts)?:\s*", lambda m: f"{m.group(1).strip()}: " if m.group(1) else "", message)
    return message.strip().rstrip(":") or "no details were returned"


def set_provider_override(factory: Optional[Callable[[str], AIProvider]]) -> None:
    global _factory_override
    _factory_override = factory


@dataclass(frozen=True)
class AIStatus:
    configured: bool
    provider: str
    model: str
    detail: str = ""


def _model_for(task: str) -> str:
    specific = {TASK_ANALYSIS: settings.ai_model_analysis, TASK_QUESTIONS: settings.ai_model_questions, TASK_GRADING: settings.ai_model_grading, TASK_REPORTING: settings.ai_model_reporting}.get(task, "")
    if specific:
        return specific
    # AI_MODEL defaults to an OpenAI model name, which a local Ollama server does not have.
    if (settings.ai_provider or "").strip().lower() == "ollama":
        return settings.ollama_model
    return settings.ai_model


def ai_status() -> AIStatus:
    """What the admin UI should say about AI, without contacting the provider."""
    kind = (settings.ai_provider or "").strip().lower()
    if kind in ("", "none", "off", "disabled"):
        return AIStatus(False, "none", "", "No AI provider is configured (AI_PROVIDER).")
    if kind == "ollama":
        return AIStatus(True, "ollama", _model_for(TASK_ANALYSIS), settings.ollama_base_url)
    if kind == "gemini":
        ok = bool(settings.gemini_api_key)
        return AIStatus(ok, "gemini", settings.gemini_model, "" if ok else "GEMINI_API_KEY is not set.")
    if kind == "groq":
        ok = bool(settings.groq_api_key)
        return AIStatus(ok, "groq", settings.groq_model, "" if ok else "GROQ_API_KEY is not set.")
    ok = bool(settings.ai_api_key) or settings.ai_base_url.rstrip("/") != "https://api.openai.com/v1"
    return AIStatus(ok, "openai_compatible", _model_for(TASK_ANALYSIS), "" if ok else "AI_API_KEY is not set.")


def provider_for(task: str) -> AIProvider:
    if _factory_override is not None:
        return _factory_override(task)

    status = ai_status()
    if not status.configured:
        raise AIUnavailable(f"AI is not available: {status.detail}")

    kind = status.provider
    timeout, retries = settings.ai_timeout_seconds, settings.ai_max_retries
    model = _model_for(task)
    if kind == "ollama":
        return OllamaProvider(model=model, base_url=settings.ollama_base_url, timeout=max(timeout, 120), max_retries=retries)
    if kind == "gemini":
        return GeminiProvider(api_key=settings.gemini_api_key, model=model or settings.gemini_model, timeout=timeout, max_retries=retries)
    if kind == "groq":
        return GroqProvider(api_key=settings.groq_api_key, model=model or settings.groq_model, timeout=timeout, max_retries=retries)
    return OpenAICompatibleProvider(
        api_key=settings.ai_api_key, model=model, base_url=settings.ai_base_url, timeout=timeout, max_retries=retries
    )


# --------------------------------------------------------------------- structured output
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(text: str) -> Dict[str, Any]:
    """Extract the JSON object from a model reply, tolerating code fences and surrounding prose."""
    cleaned = _FENCE.sub("", (text or "").strip()).strip()
    start = cleaned.find("{")
    if start == -1:
        raise AIOutputInvalid("The model's answer contained no JSON object.")
    try:
        data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except ValueError as exc:
        raise AIOutputInvalid(f"The model's answer was not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIOutputInvalid("The model's answer was JSON, but not an object.")
    return data


@dataclass(frozen=True)
class StructuredResult:
    value: BaseModel
    provider: str
    model: str
    attempts: int


async def complete_structured(
    task: str, system: str, user: str, schema: Type[T], *, max_tokens: int = 3000, temperature: float = 0.2
) -> StructuredResult:
    """
    Ask the model for JSON matching `schema`. If the reply is malformed or fails validation,
    it is shown its own error once and asked to correct it; a second failure raises.
    """
    provider = provider_for(task)
    messages = [AIMessage(role="system", content=system), AIMessage(role="user", content=user)]
    last_error: Optional[Exception] = None

    for attempt in (1, 2):
        try:
            response = await provider.complete(
                AICompletionRequest(
                    messages=messages, temperature=temperature, max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            )
        except AIProviderError as exc:
            raise AIUnavailable(f"The AI provider failed: {brief(exc)}") from exc
        except Exception as exc:  # network errors from a provider that does not wrap them
            raise AIUnavailable(f"The AI provider could not be reached: {brief(exc)}") from exc

        try:
            value = schema.model_validate(parse_json_object(response.content))
            return StructuredResult(value=value, provider=provider.provider_name, model=response.model, attempts=attempt)
        except (AIOutputInvalid, ValidationError) as exc:
            last_error = exc
            messages = messages + [
                AIMessage(role="assistant", content=response.content[:4000]),
                AIMessage(
                    role="user",
                    content=(
                        "That reply was rejected: "
                        f"{str(exc)[:600]}\nReturn ONLY one corrected JSON object that follows the schema."
                    ),
                ),
            ]

    raise AIOutputInvalid(f"The model did not return usable output after a correction attempt: {last_error}")
