"""
Optional chunk embeddings.

Embeddings are stored so later phases (grounded reporting, semantic search) can retrieve
by meaning. The stage is OPTIONAL: with no embedding model configured it is reported as
"skipped", not failed and not faked. Vectors are stored as JSON arrays with the name of
the model that produced them, so vectors from different models are never compared.

Uses an OpenAI-compatible `/embeddings` endpoint, which covers Ollama (for example
`nomic-embed-text`), OpenAI, and most self-hosted servers.
"""

from typing import List, Optional, Protocol

import httpx

from app.core.config import settings

BATCH_SIZE = 16


class Embedder(Protocol):
    model: str

    async def embed(self, texts: List[str]) -> List[List[float]]: ...


class OpenAICompatibleEmbedder:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def embed(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout, headers={"Authorization": f"Bearer {self.api_key}"}) as http:
            for start in range(0, len(texts), BATCH_SIZE):
                batch = texts[start:start + BATCH_SIZE]
                response = await http.post(f"{self.base_url}/embeddings", json={"model": self.model, "input": batch})
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda item: item["index"])
                vectors.extend(item["embedding"] for item in data)
        if len(vectors) != len(texts):
            raise ValueError("The embedding service returned the wrong number of vectors.")
        return vectors


_override: Optional[Embedder] = None


def set_embedder_override(embedder: Optional[Embedder]) -> None:
    global _override
    _override = embedder


def get_embedder() -> Optional[Embedder]:
    """The configured embedder, or None when embeddings are not enabled."""
    if _override is not None:
        return _override
    model = settings.ai_embedding_model
    if not model:
        return None
    kind = (settings.ai_provider or "").lower()
    if kind == "ollama":
        return OpenAICompatibleEmbedder(base_url=settings.ollama_base_url + "/v1", api_key="ollama", model=model)
    if kind in ("openai_compatible", "") and (settings.ai_api_key or settings.ai_base_url):
        return OpenAICompatibleEmbedder(base_url=settings.ai_base_url, api_key=settings.ai_api_key, model=model)
    return None
