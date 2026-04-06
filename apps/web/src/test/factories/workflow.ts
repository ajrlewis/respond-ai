import { type AnswerVersion, type Confidence, type EvidenceItem, type Session } from "@/lib/api";

export function buildEvidenceItem(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    chunk_id: "chunk-1",
    document_id: "doc-1",
    document_title: "Sample Document",
    document_filename: "sample-document.md",
    chunk_index: 1,
    text: "Evidence excerpt",
    score: 0.82,
    retrieval_method: "semantic",
    metadata: {},
    ...overrides,
  };
}

export function buildAnswerVersion(overrides: Partial<AnswerVersion> = {}): AnswerVersion {
  return {
    version_id: "draft-1",
    version_number: 1,
    label: "Draft 1",
    stage: "draft",
    answer_text: "Answer body",
    content: "Answer body",
    status: "draft",
    is_current: true,
    is_approved: false,
    revision_feedback: null,
    included_chunk_ids: [],
    excluded_chunk_ids: [],
    question_type: "general",
    confidence_notes: null,
    confidence_score: 0.86,
    created_at: "2026-01-01T00:00:00.000Z",
    ...overrides,
  };
}

export function buildConfidence(overrides: Partial<Confidence> = {}): Confidence {
  return {
    score: 0.86,
    compliance_status: "passed",
    model_notes: "Model assessment",
    retrieval_notes: "Retrieval assessment",
    evidence_gaps: [],
    retrieval_strategy: null,
    coverage: "strong",
    recommended_action: "proceed",
    selected_chunk_ids: ["chunk-1"],
    rejected_chunk_ids: [],
    notes_for_drafting: [],
    ...overrides,
  };
}

export function buildSession(overrides: Partial<Session> = {}): Session {
  const {
    confidence: confidenceOverride,
    evidence: evidenceOverride,
    answer_versions: answerVersionsOverride,
    ...restOverrides
  } = overrides;
  const confidence = buildConfidence(confidenceOverride ?? {});
  const evidence = evidenceOverride ?? [buildEvidenceItem()];
  const answerVersions = answerVersionsOverride ?? [buildAnswerVersion()];

  return {
    id: "session-1",
    question_text: "How do you create value in renewable infrastructure?",
    question_type: "strategy",
    tone: "formal",
    status: "awaiting_review",
    current_node: "human_review",
    retrieval_strategy_used: "adaptive",
    retry_count: 0,
    draft_answer: "Draft response",
    final_answer: null,
    final_version_number: null,
    approved_at: null,
    reviewer_action: null,
    reviewer_id: null,
    evidence_gap_count: confidence.evidence_gaps.length,
    requires_gap_acknowledgement: confidence.evidence_gaps.length > 0,
    evidence_gaps_acknowledged: false,
    evidence_gaps_acknowledged_at: null,
    confidence_notes: "Confidence notes",
    confidence,
    retrieval_plan: {},
    evidence_evaluation: {},
    evidence,
    answer_versions: answerVersions,
    final_audit: {},
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
    ...restOverrides,
    confidence,
    evidence,
    answer_versions: answerVersions,
  };
}
