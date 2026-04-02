"""Graph state contract."""

from typing import Literal, TypedDict


class WorkflowState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    thread_id: str
    session_id: str
    question_text: str
    question_type: str
    classification: dict
    retrieval_plan: dict
    retrieval_strategy_used: str
    retrieval_debug: dict
    retry_count: int
    tone: Literal["concise", "detailed", "formal"]
    current_node: str
    retrieved_chunks: list[dict]
    retrieved_evidence: list[dict]
    selected_evidence: list[dict]
    rejected_evidence: list[dict]
    curated_evidence: list[dict]
    evidence_evaluation: dict
    evidence_synthesis: dict
    draft_answer: str
    draft_origin: Literal["initial", "revision"]
    draft_metadata: dict
    confidence_notes: str
    confidence_payload: dict
    status: str
    review_action: Literal["approve", "revise"]
    reviewer_id: str
    review_comments: str
    edited_answer: str
    excluded_evidence_keys: list[str]
    reviewed_evidence_gaps: bool
    evidence_gaps_acknowledged: bool
    revision_intent: dict
    answer_versions: list[dict]
    final_answer: str
    final_version_number: int
    approved_at: str
