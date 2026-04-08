import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.routes import response_documents as response_documents_route
from app.schemas.response_documents import (
    AIReviseRequest,
    CreateResponseDocumentRequest,
    GenerateResponseDocumentRequest,
    SaveResponseVersionRequest,
)


def _build_document_payload() -> dict:
    now = datetime.now(UTC)
    question_id = uuid4()
    version_id = uuid4()
    section_id = uuid4()
    return {
        "id": uuid4(),
        "title": "Sample Response Draft",
        "source_filename": "sample.md",
        "status": "draft_ready",
        "created_at": now,
        "updated_at": now,
        "questions": [
            {
                "id": question_id,
                "order_index": 0,
                "extracted_text": "How do you manage risk?",
                "normalized_title": "How do you manage risk?",
            }
        ],
        "versions": [
            {
                "id": version_id,
                "version_number": 1,
                "label": "Version 1",
                "created_by": "tester",
                "parent_version_id": None,
                "is_final": False,
                "created_at": now,
            }
        ],
        "selected_version": {
            "id": version_id,
            "version_number": 1,
            "label": "Version 1",
            "created_by": "tester",
            "parent_version_id": None,
            "is_final": False,
            "created_at": now,
            "sections": [
                {
                    "id": section_id,
                    "question_id": question_id,
                    "order_index": 0,
                    "content_markdown": "Risk controls include scenario analysis.",
                    "confidence_score": 0.82,
                    "coverage_score": 0.66,
                    "evidence_refs": [],
                }
            ],
        },
    }


class _FakeService:
    def __init__(self, _db) -> None:
        self.doc_payload = _build_document_payload()
        self.version_id = self.doc_payload["versions"][0]["id"]
        self.question_id = self.doc_payload["questions"][0]["id"]
        self.calls: list[tuple[str, dict]] = []

    async def create_document(self, payload: CreateResponseDocumentRequest):
        self.calls.append(("create_document", payload.model_dump()))
        return self.doc_payload

    async def get_document(self, document_id, selected_version_id=None):
        self.calls.append(("get_document", {"document_id": str(document_id), "selected_version_id": str(selected_version_id) if selected_version_id else None}))
        if str(document_id).endswith("ffff"):
            raise LookupError("Response document not found.")
        return self.doc_payload

    async def generate_document(self, document_id, tone, created_by, progress=None):
        self.calls.append(("generate_document", {"document_id": str(document_id), "tone": tone, "created_by": created_by}))
        if progress is not None:
            await progress("retrieve_supporting_material", "Retrieve supporting material", "running")
        return self.doc_payload

    async def list_versions(self, document_id):
        self.calls.append(("list_versions", {"document_id": str(document_id)}))
        return self.doc_payload["versions"]

    async def save_new_version(self, document_id, payload: SaveResponseVersionRequest):
        self.calls.append(("save_new_version", {"document_id": str(document_id), "payload": payload.model_dump(mode="json")}))
        return self.doc_payload

    async def approve_version(self, document_id, version_id):
        self.calls.append(("approve_version", {"document_id": str(document_id), "version_id": str(version_id)}))
        return self.doc_payload

    async def delete_version(self, document_id, version_id):
        self.calls.append(("delete_version", {"document_id": str(document_id), "version_id": str(version_id)}))
        return self.doc_payload

    async def compare_versions(self, document_id, left_version_id, right_version_id):
        self.calls.append(("compare_versions", {"document_id": str(document_id), "left_version_id": str(left_version_id), "right_version_id": str(right_version_id)}))
        return {
            "left": self.doc_payload["versions"][0],
            "right": self.doc_payload["versions"][0],
            "segments": [{"kind": "same", "text": "same"}],
            "section_diffs": [],
        }

    async def ai_revise(self, document_id, payload: AIReviseRequest, progress=None):
        self.calls.append(("ai_revise", {"document_id": str(document_id), "payload": payload.model_dump(mode="json")}))
        if progress is not None:
            await progress("analyze_revision_request", "Analyze revision request", "running")
        return {
            "base_version_id": self.version_id,
            "revised_sections": [
                {
                    "question_id": self.question_id,
                    "content_markdown": "Revised text",
                    "confidence_score": 0.9,
                    "coverage_score": 0.7,
                    "evidence_refs": [],
                }
            ],
        }


def test_response_document_routes_use_service(monkeypatch) -> None:
    fake_service = _FakeService(SimpleNamespace())

    monkeypatch.setattr(response_documents_route, "ResponseDocumentService", lambda db: fake_service)

    document_id = fake_service.doc_payload["id"]
    version_id = fake_service.version_id

    created = asyncio.run(
        response_documents_route.create_response_document(
            payload=CreateResponseDocumentRequest(title="My draft", questions=["How do you manage risk?"]),
            db=SimpleNamespace(),
        )
    )
    assert created["title"] == "Sample Response Draft"

    loaded = asyncio.run(
        response_documents_route.get_response_document(document_id=document_id, selected_version_id=None, db=SimpleNamespace())
    )
    assert loaded["status"] == "draft_ready"

    generated = asyncio.run(
        response_documents_route.generate_response_document(
            document_id=document_id,
            payload=GenerateResponseDocumentRequest(tone="formal", created_by="tester"),
            db=SimpleNamespace(),
        )
    )
    assert generated["versions"][0]["label"] == "Version 1"

    versions = asyncio.run(
        response_documents_route.list_response_document_versions(document_id=document_id, db=SimpleNamespace())
    )
    assert versions[0]["version_number"] == 1

    approved = asyncio.run(
        response_documents_route.approve_response_document_version(
            document_id=document_id,
            version_id=version_id,
            db=SimpleNamespace(),
        )
    )
    assert approved["status"] == "draft_ready"

    saved = asyncio.run(
        response_documents_route.save_response_document_version(
            document_id=document_id,
            payload=SaveResponseVersionRequest(),
            db=SimpleNamespace(),
        )
    )
    assert saved["selected_version"]["label"] == "Version 1"

    deleted = asyncio.run(
        response_documents_route.delete_response_document_version(
            document_id=document_id,
            version_id=version_id,
            db=SimpleNamespace(),
        )
    )
    assert deleted["title"] == "Sample Response Draft"

    compared = asyncio.run(
        response_documents_route.compare_response_document_versions(
            document_id=document_id,
            left_version_id=version_id,
            right_version_id=version_id,
            db=SimpleNamespace(),
        )
    )
    assert compared["segments"][0]["kind"] == "same"

    revised = asyncio.run(
        response_documents_route.ai_revise_response_document(
            document_id=document_id,
            payload=AIReviseRequest(instruction="Make this tighter."),
            db=SimpleNamespace(),
        )
    )
    assert revised["revised_sections"][0]["content_markdown"] == "Revised text"
    assert len(fake_service.calls) >= 7


def test_response_document_route_maps_lookup_error_to_404(monkeypatch) -> None:
    fake_service = _FakeService(SimpleNamespace())
    missing_doc_id = UUID("00000000-0000-0000-0000-00000000ffff")

    monkeypatch.setattr(response_documents_route, "ResponseDocumentService", lambda db: fake_service)

    try:
        asyncio.run(
            response_documents_route.get_response_document(
                document_id=missing_doc_id,
                selected_version_id=None,
                db=SimpleNamespace(),
            )
        )
        raise AssertionError("Expected HTTPException for missing document.")
    except HTTPException as exc:
        assert exc.status_code == 404
