"""Backward-compatible LLM service built on provider-agnostic AI layer."""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.chat import get_chat_model, get_structured_model

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class LLMService:
    """Compatibility wrapper around new purpose-based chat model clients."""

    @staticmethod
    def _purpose(purpose: str) -> str:
        normalized = (purpose or "").strip()
        if normalized in {"classification", "cross_reference", "drafting", "revision", "evaluation", "polish", "draft_metadata", "revision_intent"}:
            return normalized
        if "classify" in normalized:
            return "classification"
        if "revise" in normalized:
            return "revision"
        if "draft" in normalized:
            return "drafting"
        if "cross" in normalized or "evidence" in normalized:
            return "cross_reference"
        if "eval" in normalized:
            return "evaluation"
        if "polish" in normalized:
            return "polish"
        return "drafting"

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        purpose: str = "drafting",
        request_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Synchronous compatibility call."""

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():  # pragma: no cover - defensive compatibility path
            raise RuntimeError("LLMService.complete cannot run inside an active event loop.")
        return asyncio.run(
            self.acomplete(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                purpose=purpose,
                request_metadata=request_metadata,
            )
        )

    async def acomplete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        purpose: str = "drafting",
        request_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Async compatibility call."""

        chat = get_chat_model(purpose=self._purpose(purpose))  # type: ignore[arg-type]
        return await chat.ainvoke(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            request_metadata=request_metadata,
        )

    async def acomplete_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_format: type[StructuredOutputT],
        temperature: float = 0.2,
        purpose: str = "drafting",
        request_metadata: dict[str, Any] | None = None,
    ) -> StructuredOutputT:
        """Async structured compatibility call."""

        structured = get_structured_model(schema=response_format, purpose=self._purpose(purpose))  # type: ignore[arg-type]
        return await structured.ainvoke(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            request_metadata=request_metadata,
        )
