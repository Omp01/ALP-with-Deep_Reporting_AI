"""Model selection per provider, and the Gemini output budget (found by running against a real Gemini key)."""
from app.core.config import settings
from app.ingestion import ai
from shared.schemas.ai_provider import _thinks


def _select(monkeypatch, provider, **overrides):
    monkeypatch.setattr(settings, "ai_provider", provider)
    for k, v in overrides.items():
        monkeypatch.setattr(settings, k, v)
    return ai._model_for(ai.TASK_REPORTING)


def test_gemini_uses_the_gemini_model_not_the_openai_default(monkeypatch):
    assert _select(monkeypatch, "gemini", ai_model="gpt-4o-mini", gemini_model="gemini-x", ai_model_reporting="") == "gemini-x"


def test_groq_and_ollama_use_their_own_models(monkeypatch):
    assert _select(monkeypatch, "groq", ai_model="gpt-4o-mini", groq_model="g-70b", ai_model_reporting="") == "g-70b"
    assert _select(monkeypatch, "ollama", ai_model="gpt-4o-mini", ollama_model="llama3.1", ai_model_reporting="") == "llama3.1"


def test_openai_compatible_uses_ai_model_and_a_task_override_wins(monkeypatch):
    assert _select(monkeypatch, "openai_compatible", ai_model="gpt-4o-mini", ai_model_reporting="") == "gpt-4o-mini"
    assert _select(monkeypatch, "gemini", gemini_model="gemini-x", ai_model_reporting="special") == "special"


def test_thinking_models_get_output_headroom():
    assert _thinks("gemini-3.5-flash") and _thinks("gemini-2.5-pro") and _thinks("gemini-flash-latest")
    assert not _thinks("gemini-1.5-flash") and not _thinks("")
