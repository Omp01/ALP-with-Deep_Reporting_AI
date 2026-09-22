"""
AI Provider abstraction layer.

All AI-dependent code uses this interface — never a specific provider.
Configuration selects the concrete implementation at startup.
"""
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field


class AIMessage(BaseModel):
    """A single message in an AI conversation."""
    role: str  # "system", "user", "assistant"
    content: str


class AICompletionRequest(BaseModel):
    """Request to generate a text completion."""
    messages: list[AIMessage]
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1)
    response_format: Optional[dict[str, str]] = None  # {"type": "json_object"}


class AICompletionResponse(BaseModel):
    """Response from an AI completion request."""
    content: str
    model: str
    usage: dict[str, int] = {}  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: str = "stop"
    latency_ms: int = 0


class AIProviderError(Exception):
    """Raised when the AI provider is unavailable or returns an error."""
    def __init__(self, message: str, provider: str, retryable: bool = True):
        self.provider = provider
        self.retryable = retryable
        super().__init__(message)


class AIProvider(ABC):
    """
    Abstract interface for AI text generation providers.
    All services depend on this interface, not on a specific provider.
    """

    @abstractmethod
    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        """Generate a text completion from the given messages."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is available."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of this provider."""
        ...


class OpenAICompatibleProvider(AIProvider):
    """
    Provider implementation for any OpenAI-compatible API.
    Works with: OpenAI, Groq, Together, Ollama, vLLM, etc.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 30,
        max_retries: int = 3,
        verify_ssl: Optional[bool] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        if verify_ssl is not None:
            self.verify_ssl = verify_ssl
        else:
            self.verify_ssl = os.getenv("VERIFY_SSL", "false").lower() in ("true", "1")
        self._client = None

    async def _get_client(self):
        """Lazy-init the HTTP client."""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        return self._client

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        """Send a completion request to the OpenAI-compatible endpoint."""
        import time
        import httpx

        client = await self._get_client()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            payload["response_format"] = request.response_format

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                start = time.monotonic()
                response = await client.post("/chat/completions", json=payload)
                latency_ms = int((time.monotonic() - start) * 1000)

                if response.status_code == 429:
                    # Rate limited — wait and retry
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue

                response.raise_for_status()
                data = response.json()

                return AICompletionResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=data.get("model", self.model),
                    usage=data.get("usage", {}),
                    finish_reason=data["choices"][0].get("finish_reason", "stop"),
                    latency_ms=latency_ms,
                )

            except httpx.TimeoutException as e:
                last_error = e
                continue
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    continue
                raise AIProviderError(
                    message=f"AI provider error: {e.response.status_code} {e.response.text}",
                    provider=self.provider_name,
                    retryable=False,
                )
            except Exception as e:
                last_error = e
                continue

        raise AIProviderError(
            message=f"AI provider failed after {self.max_retries} attempts: {last_error}",
            provider=self.provider_name,
            retryable=True,
        )

    async def health_check(self) -> bool:
        """Quick check that the API is reachable."""
        try:
            client = await self._get_client()
            response = await client.get("/models")
            return response.status_code == 200
        except Exception:
            return False

    @property
    def provider_name(self) -> str:
        return f"openai_compatible ({self.base_url})"

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """Helper to generate text from a prompt."""
        messages = []
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))
        messages.append(AIMessage(role="user", content=prompt))

        req = AICompletionRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        resp = await self.complete(req)
        return resp.content

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


class GroqProvider(OpenAICompatibleProvider):
    """
    Provider implementation for Groq Cloud API.
    Fast inference using Llama 3 / Mixtral models.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout: int = 30,
        max_retries: int = 3,
        verify_ssl: Optional[bool] = None,
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
        )

    @property
    def provider_name(self) -> str:
        return f"groq ({self.model})"


class OllamaProvider(OpenAICompatibleProvider):
    """
    A local model served by Ollama (https://ollama.com), through its OpenAI-compatible API.
    Free, private, and needs no API key: the zero-cost development provider.
    """

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = "http://127.0.0.1:11434",
        timeout: int = 120,
        max_retries: int = 2,
    ):
        super().__init__(
            api_key="ollama",  # ignored by Ollama; the client still sends a bearer header
            model=model,
            base_url=base_url.rstrip("/") + "/v1",
            timeout=timeout,
            max_retries=max_retries,
        )

    @property
    def provider_name(self) -> str:
        return f"ollama ({self.model})"


def _thinks(model: str) -> bool:
    """Gemini models from 2.5 onwards spend part of the output budget on thinking."""
    name = (model or "").lower()
    return any(tag in name for tag in ("gemini-2.5", "gemini-3", "flash-latest", "pro-latest"))


class GeminiProvider(AIProvider):
    """
    Provider implementation for Google Gemini REST API.
    Supports gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash, etc.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.6-flash",
        timeout: int = 45,
        max_retries: int = 3,
        verify_ssl: Optional[bool] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        if verify_ssl is not None:
            self.verify_ssl = verify_ssl
        else:
            self.verify_ssl = os.getenv("VERIFY_SSL", "false").lower() in ("true", "1")
        self._client = None

    @property
    def provider_name(self) -> str:
        return f"gemini ({self.model})"

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=self.timeout, verify=self.verify_ssl)
        return self._client

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        import time
        import httpx

        client = await self._get_client()
        contents = []
        system_instruction = None

        for m in request.messages:
            if m.role == "system":
                system_instruction = {"parts": [{"text": m.content}]}
            elif m.role == "assistant":
                contents.append({"role": "model", "parts": [{"text": m.content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": m.content}]})

        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Generate summary"}]})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        gen_config: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
        }
        if _thinks(self.model):
            gen_config["thinkingConfig"] = {"thinkingBudget": 0}

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": gen_config,
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        if request.response_format and request.response_format.get("type") == "json_object":
            payload["generationConfig"]["responseMimeType"] = "application/json"


        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                start = time.monotonic()
                response = await client.post(url, json=payload, headers={"x-goog-api-key": self.api_key})
                latency_ms = int((time.monotonic() - start) * 1000)

                if response.status_code == 429:
                    if "PerDay" in response.text:
                        # A daily quota does not clear by waiting a few seconds: fail at once, and say so.
                        raise AIProviderError(
                            message=f"Gemini's daily request quota for {self.model} is used up. Try again tomorrow, choose another model, or use a key with billing enabled.",
                            provider=self.provider_name,
                            retryable=False,
                        )
                    import asyncio
                    last_error = RuntimeError("Gemini is rate limiting requests (429)")
                    await asyncio.sleep(2 ** attempt)
                    continue

                response.raise_for_status()
                data = response.json()

                candidates = data.get("candidates", [])
                content = ""
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    content = "".join(p.get("text", "") for p in parts if not p.get("thought"))

                usage_meta = data.get("usageMetadata", {})
                usage = {
                    "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                    "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                    "total_tokens": usage_meta.get("totalTokenCount", 0),
                }

                return AICompletionResponse(
                    content=content,
                    model=self.model,
                    usage=usage,
                    finish_reason=candidates[0].get("finishReason", "stop") if candidates else "stop",
                    latency_ms=latency_ms,
                )
            except AIProviderError:
                raise
            except httpx.TimeoutException as e:
                last_error = e
                continue
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    continue
                raise AIProviderError(
                    message=f"Gemini provider error: {e.response.status_code} {e.response.text}",
                    provider=self.provider_name,
                    retryable=False,
                )
            except Exception as e:
                last_error = e
                continue

        raise AIProviderError(
            message=f"Gemini provider failed after {self.max_retries} attempts: {last_error}",
            provider=self.provider_name,
            retryable=True,
        )

    async def health_check(self) -> bool:
        return bool(self.api_key)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))
        messages.append(AIMessage(role="user", content=prompt))

        req = AICompletionRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        resp = await self.complete(req)
        return resp.content

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


def get_ai_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> AIProvider:
    """Factory function returning configured AIProvider implementation (Gemini, Groq, or OpenAI)."""
    import os
    from pathlib import Path
    try:
        from dotenv import load_dotenv
        root_env = Path(__file__).resolve().parents[2] / ".env"
        if root_env.exists():
            load_dotenv(root_env)
        else:
            load_dotenv()
    except Exception:
        pass

    selected = (provider_name or os.getenv("AI_PROVIDER", "")).strip().lower()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("AI_API_KEY", "").strip()

    # 0. Local Ollama
    if selected == "ollama":
        return OllamaProvider(
            model=model or os.getenv("OLLAMA_MODEL") or os.getenv("AI_MODEL") or "llama3.1",
            base_url=base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        )

    # 1. Google Gemini
    if selected == "gemini" or (not selected and gemini_key):
        return GeminiProvider(
            api_key=api_key or gemini_key,
            model=model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        )

    # 2. Groq Cloud
    if selected == "groq" or (not selected and groq_key):
        return GroqProvider(
            api_key=api_key or groq_key,
            model=model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        )

    # 3. Default OpenAI-compatible
    key = api_key or openai_key
    mod = model or os.getenv("AI_MODEL", "gpt-4o-mini")
    url = base_url or os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    return OpenAICompatibleProvider(api_key=key, model=mod, base_url=url)
