"""Route helper functions."""

from app.db.models import RFPSession
from app.schemas.documents import EvidenceChunk
from app.schemas.sessions import AnswerVersionOut, ConfidenceOut, SessionOut
from app.services.draft_history import list_session_drafts


def session_to_schema(session: RFPSession) -> SessionOut:
    """Convert DB session model to API schema."""

    evidence_items = []
    for item in session.evidence_payload or []:
        evidence_items.append(
            EvidenceChunk(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                document_title=item["document_title"],
                document_filename=item["document_filename"],
                chunk_index=item["chunk_index"],
                text=item["text"],
                score=item["score"],
                retrieval_method=item["retrieval_method"],
                excluded_by_reviewer=bool(item.get("excluded_by_reviewer", False)),
                metadata=item.get("metadata", {}),
            )
        )

    confidence = ConfidenceOut.model_validate(getattr(session, "confidence_payload", {}) or {})
    evidence_gap_count = len(confidence.evidence_gaps)
    requires_gap_acknowledgement = evidence_gap_count > 0
    evidence_gaps_acknowledged = bool(getattr(session, "evidence_gaps_acknowledged", False))
    if not requires_gap_acknowledgement:
        evidence_gaps_acknowledged = True

    answer_versions = [AnswerVersionOut.model_validate(item) for item in list_session_drafts(session)]

    return SessionOut(
        id=session.id,
        question_text=session.question_text,
        question_type=session.question_type,
        tone=session.tone,
        status=session.status,
        current_node=session.current_node,
        draft_answer=session.draft_answer,
        final_answer=session.final_answer,
        final_version_number=getattr(session, "final_version_number", None),
        approved_at=getattr(session, "approved_at", None),
        reviewer_action=getattr(session, "reviewer_action", None),
        reviewer_id=getattr(session, "reviewer_id", None),
        evidence_gap_count=evidence_gap_count,
        requires_gap_acknowledgement=requires_gap_acknowledgement,
        evidence_gaps_acknowledged=evidence_gaps_acknowledged,
        evidence_gaps_acknowledged_at=getattr(session, "evidence_gaps_acknowledged_at", None),
        confidence_notes=session.confidence_notes,
        confidence=confidence,
        evidence=evidence_items,
        answer_versions=answer_versions,
        final_audit=getattr(session, "final_audit_payload", {}) or {},
        created_at=session.created_at,
        updated_at=session.updated_at,
    )
