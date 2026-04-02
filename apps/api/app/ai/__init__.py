"""Provider-agnostic AI layer exports."""

from app.ai.chat import get_chat_model, get_structured_model
from app.ai.embeddings import get_embedding_model

__all__ = ["get_chat_model", "get_embedding_model", "get_structured_model"]
