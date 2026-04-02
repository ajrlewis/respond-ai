from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.routes.utils import session_to_schema


def test_session_to_schema_includes_current_node() -> None:
    now = datetime.now(UTC)
    session = SimpleNamespace(
        id=uuid4(),
        question_text="How do you manage portfolio risk?",
        question_type="risk",
        tone="formal",
        status="awaiting_review",
        current_node="draft_response",
        draft_answer="Draft answer",
        final_answer=None,
        confidence_notes="Confidence notes",
        evidence_payload=[],
        created_at=now,
        updated_at=now,
    )

    payload = session_to_schema(session)

    assert payload.current_node == "draft_response"
    assert payload.status == "awaiting_review"
    assert payload.confidence.evidence_gaps == []
    assert payload.evidence_gap_count == 0
    assert payload.requires_gap_acknowledgement is False
    assert payload.evidence_gaps_acknowledged is True
    assert payload.evidence_gaps_acknowledged_at is None
    assert payload.answer_versions == []
