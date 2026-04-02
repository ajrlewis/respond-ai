"""Google provider implementation through LangChain Google GenAI adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.ai.providers.base import (
    AIConfigurationError,
    AIProvider,
    AIProviderError,
    ChatCompletionResult,
    EmbeddingResult,
    StructuredCompletionResult,
    StructuredOutputT,
)
from app.ai.usage import (
    estimate_text_tokens,
    estimate_texts_tokens,
    extract_usage_payload,
    normalize_usage_payload,
)


def _coerce_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        rows: list[str] = []
        for item in content:
            if isinstance(item, str):
                rows.append(item)
            elif isinstance(item, Mapping):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    rows.append(text_value)
        return "\n".join(row for row in rows if row.strip())
    return str(content or "")


class GoogleProvider(AIProvider):
    """Google GenAI provider for chat + embeddings."""

    name = "google"

    def __init__(self, api_key: str) -> None:
        key = api_key.strip()
        if not key:
            raise AIConfigurationError("GOOGLE_API_KEY is required when using provider=google.")
        self._api_key = key

    def _build_messages(self, *, system_prompt: str, user_prompt: str) -> list[Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    def _chat_model(self, *, model: str, temperature: float) -> Any:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AIConfigurationError(
                "langchain-google-genai is not installed. Add it to API dependencies to use provider=google."
            ) from exc

        return ChatGoogleGenerativeAI(model=model, google_api_key=self._api_key, temperature=temperature)

    def _embedding_model(self, *, model: str) -> Any:
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AIConfigurationError(
                "langchain-google-genai is not installed. Add it to API dependencies to use Google embeddings."
            ) from exc

        return GoogleGenerativeAIEmbeddings(model=model, google_api_key=self._api_key)

    async def acomplete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> ChatCompletionResult:
        try:
            chat = self._chat_model(model=model, temperature=temperature)
            message = await chat.ainvoke(self._build_messages(system_prompt=system_prompt, user_prompt=user_prompt))
        except Exception as exc:
            raise AIProviderError(f"Google chat completion failed: {exc}") from exc

        text = _coerce_text(getattr(message, "content", ""))
        usage = normalize_usage_payload(
            extract_usage_payload(message),
            input_fallback_tokens=estimate_text_tokens(system_prompt) + estimate_text_tokens(user_prompt),
            output_fallback_tokens=estimate_text_tokens(text),
        )
        return ChatCompletionResult(
            text=text,
            usage=usage,
            response_payload={
                "content": text,
                "response_metadata": dict(getattr(message, "response_metadata", {}) or {}),
            },
        )

    async def acomplete_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[StructuredOutputT],
        temperature: float,
    ) -> StructuredCompletionResult[StructuredOutputT]:
        chat = self._chat_model(model=model, temperature=temperature)
        messages = self._build_messages(system_prompt=system_prompt, user_prompt=user_prompt)

        try:
            structured = chat.with_structured_output(response_schema, include_raw=True)
            output = await structured.ainvoke(messages)
        except TypeError:
            try:
                structured = chat.with_structured_output(response_schema)
                output = await structured.ainvoke(messages)
            except Exception as exc:
                raise AIProviderError(f"Google structured completion failed: {exc}") from exc
        except Exception as exc:
            raise AIProviderError(f"Google structured completion failed: {exc}") from exc

        parsed: BaseModel | dict | Any
        raw_message: Any = None
        if isinstance(output, Mapping) and "parsed" in output:
            parsed = output.get("parsed")
            raw_message = output.get("raw")
        else:
            parsed = output

        if parsed is None:
            raise AIProviderError(f"Google structured completion returned no parsed payload for {response_schema.__name__}.")

        if isinstance(parsed, response_schema):
            parsed_model = parsed
        else:
            parsed_model = response_schema.model_validate(parsed)

        usage = normalize_usage_payload(
            extract_usage_payload(raw_message or parsed_model),
            input_fallback_tokens=estimate_text_tokens(system_prompt) + estimate_text_tokens(user_prompt),
        )
        return StructuredCompletionResult(
            parsed=parsed_model,
            usage=usage,
            response_payload={
                "parsed": parsed_model.model_dump(),
                "raw_response_metadata": dict(getattr(raw_message, "response_metadata", {}) or {}),
            },
        )

    def embed_texts(
        self,
        *,
        model: str,
        texts: list[str],
    ) -> EmbeddingResult:
        try:
            embeddings = self._embedding_model(model=model)
            vectors = embeddings.embed_documents(texts)
        except Exception as exc:
            raise AIProviderError(f"Google embeddings failed: {exc}") from exc

        usage = normalize_usage_payload(
            {},
            input_fallback_tokens=estimate_texts_tokens(texts),
            output_fallback_tokens=0,
        )
        return EmbeddingResult(
            vectors=vectors,
            usage=usage,
            response_payload={
                "embedding_count": len(vectors),
                "vector_dimensions": len(vectors[0]) if vectors else 0,
            },
        )

    async def aembed_texts(
        self,
        *,
        model: str,
        texts: list[str],
    ) -> EmbeddingResult:
        embeddings = self._embedding_model(model=model)
        try:
            if hasattr(embeddings, "aembed_documents"):
                vectors = await embeddings.aembed_documents(texts)
            else:  # pragma: no cover - compatibility path
                import asyncio

                vectors = await asyncio.to_thread(embeddings.embed_documents, texts)
        except Exception as exc:
            raise AIProviderError(f"Google async embeddings failed: {exc}") from exc

        usage = normalize_usage_payload(
            {},
            input_fallback_tokens=estimate_texts_tokens(texts),
            output_fallback_tokens=0,
        )
        return EmbeddingResult(
            vectors=vectors,
            usage=usage,
            response_payload={
                "embedding_count": len(vectors),
                "vector_dimensions": len(vectors[0]) if vectors else 0,
            },
        )
