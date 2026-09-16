"""
AI Provider abstraction layer.

All AI-dependent code uses this interface — never a specific provider.
Configuration selects the concrete implementation at startup.
"""
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
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
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


def get_ai_provider(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> OpenAICompatibleProvider:
    """Factory function returning configured AIProvider implementation."""
    import os
    key = api_key or os.getenv("AI_API_KEY", "")
    mod = model or os.getenv("AI_MODEL", "gpt-4o-mini")
    url = base_url or os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    return OpenAICompatibleProvider(api_key=key, model=mod, base_url=url)
