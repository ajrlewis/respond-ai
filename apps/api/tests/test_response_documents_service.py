from types import SimpleNamespace

from app.services import response_documents as response_documents_service


def test_response_document_service_initializes_retrieval_with_embedding_service(monkeypatch) -> None:
    sentinel_db = SimpleNamespace()
    sentinel_embedding_service = SimpleNamespace()
    captured: dict[str, object] = {}

    class _StubRetrievalService:
        def __init__(self, db, embedding_service=None) -> None:
            captured["db"] = db
            captured["embedding_service"] = embedding_service

    monkeypatch.setattr(
        response_documents_service,
        "optional_embedding_service",
        lambda: sentinel_embedding_service,
    )
    monkeypatch.setattr(response_documents_service, "RetrievalService", _StubRetrievalService)

    service = response_documents_service.ResponseDocumentService(sentinel_db)

    assert captured["db"] is sentinel_db
    assert captured["embedding_service"] is sentinel_embedding_service
    assert isinstance(service.retrieval, _StubRetrievalService)
