"""Backward-compatible embedding service built on provider-agnostic AI layer."""

from __future__ import annotations

from typing import Any

from app.ai.embeddings import EmbeddingModelClient, get_embedding_model


class EmbeddingService:
    """Embedding helper used by retrieval and ingestion services."""

    def __init__(self, model: EmbeddingModelClient | None = None) -> None:
        self._model = model or get_embedding_model()

    def embed_text(
        self,
        text: str,
        *,
        purpose: str = "embedding",
        request_metadata: dict[str, Any] | None = None,
    ) -> list[float]:
        return self._model.embed_text(text, purpose=purpose, request_metadata=request_metadata)

    def embed_texts(
        self,
        texts: list[str],
        *,
        purpose: str = "embedding",
        request_metadata: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        return self._model.embed_texts(texts, purpose=purpose, request_metadata=request_metadata)

    async def aembed_text(
        self,
        text: str,
        *,
        purpose: str = "embedding",
        request_metadata: dict[str, Any] | None = None,
    ) -> list[float]:
        return await self._model.aembed_text(text, purpose=purpose, request_metadata=request_metadata)

    async def aembed_texts(
        self,
        texts: list[str],
        *,
        purpose: str = "embedding",
        request_metadata: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        return await self._model.aembed_texts(texts, purpose=purpose, request_metadata=request_metadata)
