import asyncio
import types
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.graph.nodes import WorkflowNodes


class _ExpiringFinalizeSession:
    def __init__(self) -> None:
        self._id = uuid4()
        self.expired = False
        self.draft_answer = "Draft output"
        self.final_answer: str | None = None
        self.answer_versions_payload = [
            {
                "version_id": "d1",
                "version_number": 1,
                "answer_text": "Draft output",
                "content": "Draft output",
                "stage": "draft",
                "status": "draft",
            }
        ]
        self.evidence_payload = []
        self.status = "awaiting_finalization"

    @property
    def id(self):  # pragma: no cover - guard for regression path
        if self.expired:
            raise RuntimeError("Expired ORM attribute access")
        return self._id


def test_finalize_response_does_not_access_expired_session_attrs() -> None:
    fake_session = _ExpiringFinalizeSession()

    class FakeDB:
        async def get(self, _model, _session_id):
            return fake_session

        async def execute(self, _stmt):
            class _Result:
                def scalars(self):
                    return self

                def all(self):
                    return []

            return _Result()

        async def commit(self):
            fake_session.expired = True

    class FakeContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    nodes = WorkflowNodes(session_factory=None)  # type: ignore[arg-type]

    async def fake_set_current_node(_session_id: str | None, _node_name: str) -> None:
        return None

    def fake_db(self):
        return FakeContext()

    nodes._set_current_node = fake_set_current_node  # type: ignore[assignment]
    nodes._db = types.MethodType(fake_db, nodes)  # type: ignore[assignment]

    state = {
        "session_id": str(uuid4()),
        "draft_answer": "Draft output",
        "edited_answer": "",
    }
    result = asyncio.run(nodes.finalize_response(state))

    assert result["status"] == "approved"
    assert result["final_answer"] == "Draft output"
    assert result["final_version_number"] == 1


def test_finalize_response_persists_audit_snapshot_and_lock_metadata() -> None:
    session_id = uuid4()
    review_id = uuid4()
    now = datetime.now(UTC)

    fake_session = SimpleNamespace(
        id=session_id,
        draft_answer="Approved draft text.",
        final_answer=None,
        final_version_number=None,
        approved_at=None,
        reviewer_action=None,
        reviewer_id=None,
        final_audit_payload={},
        status="awaiting_finalization",
        evidence_payload=[
            {
                "chunk_id": "chunk-1",
                "document_id": str(uuid4()),
                "document_title": "Policy",
                "document_filename": "policy.md",
                "chunk_index": 2,
                "text": "Evidence text",
                "score": 0.8,
                "retrieval_method": "semantic",
                "excluded_by_reviewer": False,
                "metadata": {},
            }
        ],
        answer_versions_payload=[
            {
                "version_id": "d1",
                "version_number": 1,
                "answer_text": "Approved draft text.",
                "content": "Approved draft text.",
                "stage": "draft",
                "status": "draft",
            }
        ],
    )
    fake_review = SimpleNamespace(
        id=review_id,
        reviewer_action="approve",
        reviewer_id="reviewer-123",
        review_comments="Looks good.",
        edited_answer=None,
        excluded_evidence_keys=[],
        reviewed_evidence_gaps=True,
        created_at=now,
    )

    class FakeDB:
        async def get(self, _model, _session_id):
            return fake_session

        async def execute(self, _stmt):
            class _Result:
                def scalars(self):
                    return self

                def all(self):
                    return [fake_review]

            return _Result()

        async def commit(self):
            return None

    class FakeContext:
        async def __aenter__(self):
            return FakeDB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    nodes = WorkflowNodes(session_factory=None)  # type: ignore[arg-type]

    async def fake_set_current_node(_session_id: str | None, _node_name: str) -> None:
        return None

    def fake_db(self):
        return FakeContext()

    nodes._set_current_node = fake_set_current_node  # type: ignore[assignment]
    nodes._db = types.MethodType(fake_db, nodes)  # type: ignore[assignment]

    result = asyncio.run(
        nodes.finalize_response(
            {
                "session_id": str(session_id),
                "draft_answer": "Approved draft text.",
                "confidence_notes": "Confidence note.",
                "confidence_payload": {"score": 0.82},
                "review_comments": "Looks good.",
                "reviewer_id": "reviewer-123",
            }
        )
    )

    assert result["status"] == "approved"
    assert result["final_version_number"] == 1
    assert fake_session.status == "approved"
    assert fake_session.final_answer == "Approved draft text."
    assert fake_session.final_version_number == 1
    assert fake_session.reviewer_action == "approve"
    assert fake_session.reviewer_id == "reviewer-123"
    assert fake_session.approved_at is not None
    assert fake_session.final_audit_payload["version_number"] == 1
    assert fake_session.final_audit_payload["reviewer_action"] == "approve"
    assert fake_session.final_audit_payload["selected_evidence"][0]["chunk_id"] == "chunk-1"
    assert fake_session.final_audit_payload["review_history"][0]["id"] == str(review_id)
    assert fake_session.answer_versions_payload[0]["status"] == "approved"
    assert fake_session.answer_versions_payload[0]["stage"] == "final"
