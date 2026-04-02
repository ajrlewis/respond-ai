"""Graph tool-like retrieval functions."""

from __future__ import annotations

import logging
from time import perf_counter
from uuid import UUID

from app.services.observability import log_tool_run
from app.services.retrieval import RetrievalService, chunk_to_dict

logger = logging.getLogger(__name__)


async def semantic_search(retrieval: RetrievalService, query: str, top_k: int) -> list[dict]:
    """Semantic pgvector search."""

    logger.debug("Semantic search invoked top_k=%d query_chars=%d", top_k, len(query))
    started = perf_counter()
    status = "success"
    results: list[dict] = []

    try:
        results = [chunk_to_dict(item) for item in await retrieval.semantic_search(query=query, top_k=top_k)]
        logger.debug("Semantic search returned count=%d", len(results))
        return results
    except Exception:
        status = "error"
        raise
    finally:
        latency_ms = int((perf_counter() - started) * 1000)
        await log_tool_run(
            tool_name="semantic_search",
            tool_type="semantic_search",
            query_text=query,
            arguments={"top_k": top_k},
            result_ids=[str(item.get("chunk_id", "")) for item in results],
            result_count=len(results),
            latency_ms=latency_ms,
            status=status,
            metadata={
                "scores": [float(item.get("score", 0.0)) for item in results[:20]],
            },
        )


async def keyword_search(retrieval: RetrievalService, query: str, top_k: int) -> list[dict]:
    """Keyword FTS search."""

    logger.debug("Keyword search invoked top_k=%d query_chars=%d", top_k, len(query))
    started = perf_counter()
    status = "success"
    results: list[dict] = []

    try:
        results = [chunk_to_dict(item) for item in await retrieval.keyword_search(query=query, top_k=top_k)]
        logger.debug("Keyword search returned count=%d", len(results))
        return results
    except Exception:
        status = "error"
        raise
    finally:
        latency_ms = int((perf_counter() - started) * 1000)
        await log_tool_run(
            tool_name="keyword_search",
            tool_type="keyword_search",
            query_text=query,
            arguments={"top_k": top_k},
            result_ids=[str(item.get("chunk_id", "")) for item in results],
            result_count=len(results),
            latency_ms=latency_ms,
            status=status,
            metadata={
                "scores": [float(item.get("score", 0.0)) for item in results[:20]],
            },
        )


async def expand_chunk_context(retrieval: RetrievalService, chunk_id: str, window: int = 1) -> list[dict]:
    """Fetch neighboring chunks for stronger citation context."""

    logger.debug("Expanding chunk context chunk_id=%s window=%d", chunk_id, window)
    started = perf_counter()
    status = "success"
    results: list[dict] = []

    try:
        results = [
            chunk_to_dict(item)
            for item in await retrieval.expand_chunk_context(chunk_id=UUID(chunk_id), window=window)
        ]
        logger.debug("Expanded chunk context count=%d chunk_id=%s", len(results), chunk_id)
        return results
    except Exception:
        status = "error"
        raise
    finally:
        latency_ms = int((perf_counter() - started) * 1000)
        await log_tool_run(
            tool_name="expand_chunk_context",
            tool_type="expand_chunk_context",
            query_text=None,
            arguments={"chunk_id": chunk_id, "window": window},
            result_ids=[str(item.get("chunk_id", "")) for item in results],
            result_count=len(results),
            latency_ms=latency_ms,
            status=status,
            metadata={},
        )
