import { type AnswerVersion, type DraftDiffSegment, type EvidenceItem, type Session } from "@/lib/api";
import { CONFIDENCE_WARNING_THRESHOLD, evidenceKey, statusLabel, tokenizeNumberedCitations } from "@/lib/workflow";

export type ReviewRailTab = "evidence" | "gaps" | "activity";

export type WorkflowActivityEvent = { id: string; timestamp: string; reason: string; node: string | null; status: string | null; error: string | null };

export type RunStageStatus = "idle" | "running" | "done" | "warning" | "failed";
export type RunStageId =
  | "retrieve_context"
  | "rank_evidence"
  | "draft_response"
  | "validate_grounding"
  | "review_confidence"
  | "finalize_answer";

export type QuestionEntity = { id: string; title: string; prompt: string; tone: Session["tone"] | "formal"; statusLabel: string; questionType: string | null; updatedAt: string | null };

export type CitationEntity = { number: number; label: string; evidenceKey: string; sourceTitle: string; excerpt: string };

export type ParagraphReviewState = "grounded" | "weak_evidence" | "unverified" | "changed_since_last_run";

export type AnswerParagraphEntity = { id: string; index: number; text: string; citationNumbers: number[]; state: ParagraphReviewState };

export type AnswerDraftEntity = { id: string; versionLabel: string; statusLabel: string; text: string; citations: CitationEntity[]; paragraphs: AnswerParagraphEntity[]; isReadOnly: boolean };

export type EvidenceChunkEntity = {
  key: string;
  chunkId: string;
  sourceTitle: string;
  documentFilename: string;
  excerpt: string;
  chunkIndex: number;
  retrievalMethod: string;
  score: number;
  citationNumber: number | null;
  status: "used" | "unused" | "excluded";
  usedInDraft: boolean;
  isExcluded: boolean;
  stale: boolean;
  matchReason: string;
};

export type GapEntity = { id: string; title: string; detail: string; severity: "info" | "warning"; acknowledged: boolean };

export type ReviewSummaryEntity = {
  confidenceScore: number | null;
  complianceStatus: Session["confidence"]["compliance_status"] | "unknown";
  evidenceCoverage: {
    cited: number;
    total: number;
    percentage: number;
  };
  citationCount: number;
  gapCount: number;
  unusedClaimsCount: number;
  staleEvidenceCount: number;
};

export type RunStageEntity = { id: RunStageId; label: string; status: RunStageStatus; startedAt: string | null; endedAt: string | null; durationMs: number | null; details: string[] };
export type RevisionEntity = { id: string; label: string; status: AnswerVersion["status"]; versionNumber: number; createdAt: string; isCurrent: boolean; isApproved: boolean; revisionFeedback: string | null };
export type ReviewWorkspaceModel = { question: QuestionEntity; draft: AnswerDraftEntity; evidence: EvidenceChunkEntity[]; gaps: GapEntity[]; summary: ReviewSummaryEntity; runStages: RunStageEntity[]; revisions: RevisionEntity[] };
export type BuildReviewWorkspaceModelArgs = {
  questionText: string; session: Session | null; answerText: string; selectedVersionLabel: string; selectedVersionStatus: string; isReadOnly: boolean;
  citationKeyByNumber: Map<number, string>; citationByEvidenceKey: Map<string, number>; citedEvidenceKeys: Set<string>; excludedEvidenceKeys: Set<string>;
  drafts: AnswerVersion[]; compareSegments: DraftDiffSegment[]; isCompareMode: boolean; activityEvents: WorkflowActivityEvent[];
};
type StageDefinition = { id: RunStageId; label: string };

const STAGES: StageDefinition[] = [
  { id: "retrieve_context", label: "Retrieve supporting material" },
  { id: "rank_evidence", label: "Rank evidence" },
  { id: "draft_response", label: "Draft response" },
  { id: "validate_grounding", label: "Review citations" },
  { id: "review_confidence", label: "Review quality" },
  { id: "finalize_answer", label: "Finalize draft" },
];

const NODE_TO_STAGE: Record<string, RunStageId> = {
  ask: "retrieve_context",
  classify_and_plan: "retrieve_context",
  classify_question: "retrieve_context",
  adaptive_retrieve: "retrieve_context",
  retrieve_evidence: "retrieve_context",
  evaluate_evidence: "rank_evidence",
  draft_response: "draft_response",
  revise_response: "draft_response",
  polish_response: "draft_response",
  cross_reference_evidence: "validate_grounding",
  human_review: "review_confidence",
  finalize_response: "finalize_answer",
};

function safeTitle(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "Untitled prompt";
  return trimmed.length > 88 ? `${trimmed.slice(0, 88).trimEnd()}...` : trimmed;
}

function complianceNeedsReview(session: Session | null): boolean {
  if (!session) return false;
  if (session.confidence.compliance_status === "needs_review") return true;
  if ((session.confidence.score ?? 1) < CONFIDENCE_WARNING_THRESHOLD) return true;
  if ((session.evidence_gap_count ?? 0) > 0) return true;
  return false;
}

function asIsoTime(value: string | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function durationMs(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const startMs = Date.parse(start);
  const endMs = Date.parse(end);
  if (Number.isNaN(startMs) || Number.isNaN(endMs)) return null;
  return Math.max(0, endMs - startMs);
}

function toStageId(node: string | null | undefined): RunStageId | null {
  if (!node) return null;
  return NODE_TO_STAGE[node] ?? null;
}

function deriveActiveStage(session: Session | null): RunStageId | null {
  if (!session) return null;
  if (session.status === "approved") return "finalize_answer";
  if (session.status === "awaiting_finalization") return "finalize_answer";
  const mapped = toStageId(session.current_node);
  if (mapped) return mapped;
  if (session.status === "awaiting_review" || session.status === "revision_requested") return "review_confidence";
  return "retrieve_context";
}

function extractChangedKeywords(compareSegments: DraftDiffSegment[]): string[] {
  const keywords = new Set<string>();

  for (const segment of compareSegments) {
    if (segment.kind === "same") continue;
    for (const rawWord of segment.text.toLowerCase().split(/[^a-z0-9]+/)) {
      const word = rawWord.trim();
      if (word.length < 6) continue;
      keywords.add(word);
    }
  }

  return Array.from(keywords).slice(0, 40);
}

function inferParagraphState(
  paragraph: string,
  citationNumbers: number[],
  citationKeyByNumber: Map<number, string>,
  evidenceByKey: Map<string, EvidenceItem>,
  isCompareMode: boolean,
  changedKeywords: string[],
): ParagraphReviewState {
  const normalized = paragraph.toLowerCase();

  if (
    isCompareMode &&
    changedKeywords.some((keyword) => normalized.includes(keyword))
  ) {
    return "changed_since_last_run";
  }

  if (!citationNumbers.length) return "unverified";

  const linkedEvidence = citationNumbers
    .map((number) => citationKeyByNumber.get(number))
    .filter((key): key is string => !!key)
    .map((key) => evidenceByKey.get(key))
    .filter((item): item is EvidenceItem => !!item);

  if (!linkedEvidence.length) return "weak_evidence";
  if (linkedEvidence.some((item) => item.score < 0.7)) return "weak_evidence";

  return "grounded";
}

function isEvidenceStale(item: EvidenceItem): boolean {
  const stale = item.metadata?.stale;
  return stale === true;
}

function confidenceGapEntities(session: Session | null, staleEvidenceCount: number): GapEntity[] {
  if (!session) return [];

  const gaps = session.confidence.evidence_gaps ?? [];
  const mapped = gaps.map((gap, index) => ({
    id: `gap-${index + 1}`,
    title: "Evidence gap",
    detail: gap,
    severity: "warning" as const,
    acknowledged: session.evidence_gaps_acknowledged,
  }));

  if (staleEvidenceCount > 0) {
    mapped.push({
      id: "stale-evidence",
      title: "Freshness warning",
      detail: `${staleEvidenceCount} evidence chunk${staleEvidenceCount === 1 ? " appears" : "s appear"} stale.`,
      severity: "warning",
      acknowledged: false,
    });
  }

  if ((session.confidence.score ?? 1) < CONFIDENCE_WARNING_THRESHOLD) {
    mapped.push({
      id: "confidence-warning",
      title: "Low confidence",
      detail: `Confidence is ${(session.confidence.score ?? 0).toFixed(2)} (below ${CONFIDENCE_WARNING_THRESHOLD.toFixed(2)}).`,
      severity: "warning",
      acknowledged: false,
    });
  }

  return mapped;
}

function stageDetails(events: WorkflowActivityEvent[]): string[] {
  return events.slice(-4).map((event) => {
    const parts = [event.reason];
    if (event.node) parts.push(event.node);
    if (event.status) parts.push(event.status);
    if (event.error) parts.push(event.error);
    return parts.join(" · ");
  });
}

function buildRunStages(session: Session | null, activityEvents: WorkflowActivityEvent[]): RunStageEntity[] {
  const eventsByStage = new Map<RunStageId, WorkflowActivityEvent[]>();
  for (const event of activityEvents) {
    const stageId = toStageId(event.node);
    if (!stageId) continue;
    const existing = eventsByStage.get(stageId) ?? [];
    existing.push(event);
    eventsByStage.set(stageId, existing);
  }

  const activeStage = deriveActiveStage(session);
  const activeIndex = activeStage ? STAGES.findIndex((stage) => stage.id === activeStage) : -1;
  const hasFailure = activityEvents.some((event) => !!event.error);

  return STAGES.map((stage, index) => {
    const stageEvents = eventsByStage.get(stage.id) ?? [];
    const first = stageEvents[0];
    const last = stageEvents[stageEvents.length - 1];
    const startedAt = asIsoTime(first?.timestamp);
    const fallbackEnd = session?.status === "approved" ? asIsoTime(session.updated_at) : null;
    const endedAt = asIsoTime(last?.timestamp) ?? fallbackEnd;

    let status: RunStageStatus = "idle";

    if (session?.status === "approved") {
      status = "done";
    } else if (activeIndex >= 0) {
      if (index < activeIndex) status = "done";
      if (index === activeIndex) status = "running";
      if (index > activeIndex) status = "idle";
    }

    if (stage.id === "review_confidence" && complianceNeedsReview(session) && status !== "idle") {
      status = "warning";
    }

    if (hasFailure && stage.id === activeStage) {
      status = "failed";
    }

    return {
      id: stage.id,
      label: stage.label,
      status,
      startedAt,
      endedAt: status === "running" ? null : endedAt,
      durationMs: status === "running" ? durationMs(startedAt, asIsoTime(session?.updated_at)) : durationMs(startedAt, endedAt),
      details: stageDetails(stageEvents),
    };
  });
}

export function buildReviewWorkspaceModel(args: BuildReviewWorkspaceModelArgs): ReviewWorkspaceModel {
  const {
    questionText,
    session,
    answerText,
    selectedVersionLabel,
    selectedVersionStatus,
    isReadOnly,
    citationKeyByNumber,
    citationByEvidenceKey,
    citedEvidenceKeys,
    excludedEvidenceKeys,
    drafts,
    compareSegments,
    isCompareMode,
    activityEvents,
  } = args;

  const evidence = session?.evidence ?? [];
  const evidenceByKey = new Map<string, EvidenceItem>(evidence.map((item) => [evidenceKey(item), item]));
  const changedKeywords = extractChangedKeywords(compareSegments);

  const citations: CitationEntity[] = [];
  const seenCitations = new Set<number>();
  for (const token of tokenizeNumberedCitations(answerText)) {
    if (token.kind !== "citation") continue;
    if (seenCitations.has(token.value)) continue;
    seenCitations.add(token.value);

    const key = citationKeyByNumber.get(token.value);
    if (!key) continue;
    const linked = evidenceByKey.get(key);
    if (!linked) continue;

    citations.push({
      number: token.value,
      label: token.label,
      evidenceKey: key,
      sourceTitle: linked.document_title || linked.document_filename,
      excerpt: linked.text,
    });
  }

  const rawParagraphs = answerText
    ? answerText
        .split(/\n{2,}/)
        .map((paragraph) => paragraph.trim())
        .filter(Boolean)
    : [];

  const paragraphs: AnswerParagraphEntity[] = rawParagraphs.map((paragraph, index) => {
    const numbers = tokenizeNumberedCitations(paragraph)
      .filter((token): token is { kind: "citation"; value: number; label: string } => token.kind === "citation")
      .map((token) => token.value);

    return {
      id: `paragraph-${index + 1}`,
      index,
      text: paragraph,
      citationNumbers: Array.from(new Set(numbers)),
      state: inferParagraphState(paragraph, numbers, citationKeyByNumber, evidenceByKey, isCompareMode, changedKeywords),
    };
  });

  const evidenceEntities: EvidenceChunkEntity[] = evidence.map((item) => {
    const key = evidenceKey(item);
    const usedInDraft = citedEvidenceKeys.has(key);
    const isExcluded = excludedEvidenceKeys.has(key);
    const citationNumber = citationByEvidenceKey.get(key) ?? null;
    const stale = isEvidenceStale(item);

    return {
      key,
      chunkId: item.chunk_id,
      sourceTitle: item.document_title || item.document_filename,
      documentFilename: item.document_filename,
      excerpt: item.text,
      chunkIndex: item.chunk_index,
      retrievalMethod: item.retrieval_method,
      score: item.score,
      citationNumber,
      status: isExcluded ? "excluded" : usedInDraft ? "used" : "unused",
      usedInDraft,
      isExcluded,
      stale,
      matchReason: `${item.retrieval_method} retrieval · score ${item.score.toFixed(2)}`,
    };
  });

  const staleEvidenceCount = evidenceEntities.filter((item) => item.stale).length;
  const gapEntities = confidenceGapEntities(session, staleEvidenceCount);

  const citationCount = citations.length;
  const evidenceCount = evidenceEntities.length;
  const unverifiedParagraphCount = paragraphs.filter((paragraph) => paragraph.state === "unverified").length;

  return {
    question: {
      id: session?.id ?? "draft-question",
      title: safeTitle(session?.question_text ?? questionText),
      prompt: session?.question_text ?? questionText,
      tone: session?.tone ?? "formal",
      statusLabel: statusLabel(session?.status ?? "draft"),
      questionType: session?.question_type ?? null,
      updatedAt: session?.updated_at ?? null,
    },
    draft: {
      id: session?.id ?? "draft-answer",
      versionLabel: selectedVersionLabel,
      statusLabel: selectedVersionStatus,
      text: answerText,
      citations,
      paragraphs,
      isReadOnly,
    },
    evidence: evidenceEntities,
    gaps: gapEntities,
    summary: {
      confidenceScore: session?.confidence?.score ?? null,
      complianceStatus: session?.confidence?.compliance_status ?? "unknown",
      evidenceCoverage: {
        cited: citationCount,
        total: evidenceCount,
        percentage: evidenceCount ? Math.round((citationCount / evidenceCount) * 100) : 0,
      },
      citationCount,
      gapCount: gapEntities.length,
      unusedClaimsCount: unverifiedParagraphCount,
      staleEvidenceCount,
    },
    runStages: buildRunStages(session, activityEvents),
    revisions: [...drafts]
      .sort((a, b) => b.version_number - a.version_number)
      .map((draft) => ({
        id: draft.version_id,
        label: draft.label,
        status: draft.status,
        versionNumber: draft.version_number,
        createdAt: draft.created_at,
        isCurrent: draft.is_current,
        isApproved: draft.is_approved,
        revisionFeedback: draft.revision_feedback,
      })),
  };
}
