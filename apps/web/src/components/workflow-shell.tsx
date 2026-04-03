"use client";

import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import {
  compareDrafts,
  askQuestion,
  fetchDrafts,
  fetchSession,
  fetchSessionByThreadId,
  reviewSession,
  type AnswerVersion,
  type DraftDiffSegment,
  type EvidenceItem,
  type Session,
  type Tone,
} from "@/lib/api";

const SAMPLE_QUESTIONS = [
  "Describe your renewable energy investment strategy and how you create value over the hold period.",
  "How do you assess ESG risks during due diligence and portfolio monitoring?",
  "Provide examples of recent investments in solar or storage infrastructure.",
];

const CITATION_PATTERN = /\[([^[\]]+)\]/g;
const NUMBERED_CITATION_PATTERN = /\[(\d+)\]/g;
const CONFIDENCE_WARNING_THRESHOLD = 0.7;

type CitationView = {
  answerText: string;
  citedEvidenceKeys: Set<string>;
  citationByEvidenceKey: Map<string, number>;
  citationKeyByNumber: Map<number, string>;
};

function statusLabel(status: Session["status"]): string {
  switch (status) {
    case "awaiting_review":
      return "Awaiting Review";
    case "revision_requested":
      return "Revision Requested";
    case "awaiting_finalization":
      return "Finalization In Progress";
    case "approved":
      return "Approved · Locked";
    default:
      return "Draft";
  }
}

function workflowSummary(status: Session["status"] | null): string {
  if (!status) return "Workflow: Not started";

  switch (status) {
    case "approved":
      return "Workflow: Approved (final)";
    case "awaiting_review":
      return "Workflow: Awaiting review";
    case "revision_requested":
      return "Workflow: Revision requested";
    case "awaiting_finalization":
      return "Workflow: Finalizing";
    default:
      return "Workflow: Draft in progress";
  }
}

function nodeProgressLabel(session: Session | null): string {
  if (!session) return "Initializing workflow...";

  switch (session.current_node) {
    case "ask":
      return "Initializing workflow...";
    case "classify_and_plan":
      return "Planning retrieval...";
    case "classify_question":
      return "Classifying question...";
    case "adaptive_retrieve":
      return "Retrieving evidence adaptively...";
    case "retrieve_evidence":
      return "Retrieving evidence...";
    case "evaluate_evidence":
      return "Evaluating evidence sufficiency...";
    case "cross_reference_evidence":
      return "Cross-checking evidence...";
    case "draft_response":
      return "Drafting response...";
    case "polish_response":
      return "Polishing tone...";
    case "human_review":
      return session.status === "awaiting_review" ? "Draft ready for review." : "Waiting for review...";
    case "revise_response":
      return "Applying revision...";
    case "finalize_response":
      return "Finalizing response...";
    default:
      if (session.status === "awaiting_review") return "Draft ready for review.";
      if (session.status === "approved") return "Final answer approved.";
      return "Running workflow...";
  }
}

function normalizeToken(value: string): string {
  return value.trim().toLowerCase();
}

function evidenceKey(item: EvidenceItem): string {
  if (item.chunk_id) {
    return item.chunk_id;
  }

  return `${normalizeToken(item.document_filename)}::${item.chunk_index}`;
}

function evidenceDocumentTokens(item: EvidenceItem): Set<string> {
  const tokens = new Set<string>();
  for (const raw of [item.document_filename, item.document_title, item.document_id]) {
    const value = normalizeToken(raw);
    if (!value) continue;
    tokens.add(value);
    const parts = value.split("/");
    const basename = parts[parts.length - 1];
    if (basename) {
      tokens.add(basename);
    }
  }
  return tokens;
}

function resolveCitationToEvidenceIndex(content: string, evidence: EvidenceItem[]): number | null {
  const citation = content.trim();
  if (!citation) return null;

  const indexedChunk = citation.match(/^(\d+)\s*#\s*chunk-(\d+)$/i);
  if (indexedChunk) {
    const sourceIndex = Number(indexedChunk[1]) - 1;
    const item = evidence[sourceIndex];
    if (!item) return null;
    return sourceIndex;
  }

  const documentChunk = citation.match(/^(.+?)\s*#\s*chunk-(\d+)$/i);
  if (documentChunk) {
    const documentToken = normalizeToken(documentChunk[1]);
    const chunkIndex = Number(documentChunk[2]);

    const exact = evidence.findIndex((item) => {
      if (item.chunk_index !== chunkIndex) return false;
      return evidenceDocumentTokens(item).has(documentToken);
    });
    if (exact >= 0) return exact;

    const documentParts = documentToken.split("/");
    const documentBasename = documentParts[documentParts.length - 1];
    const fuzzy = evidence.findIndex((item) => {
      if (item.chunk_index !== chunkIndex) return false;
      const tokens = evidenceDocumentTokens(item);
      for (const token of tokens) {
        if (token.endsWith(documentBasename) || documentBasename.endsWith(token)) return true;
      }
      return false;
    });
    if (fuzzy >= 0) return fuzzy;

    const fallback = evidence.findIndex((item) => item.chunk_index === chunkIndex);
    return fallback >= 0 ? fallback : null;
  }

  const indexedOnly = citation.match(/^(\d+)$/);
  if (indexedOnly) {
    const sourceIndex = Number(indexedOnly[1]) - 1;
    return evidence[sourceIndex] ? sourceIndex : null;
  }

  return null;
}

function buildCitationView(answerText: string, evidence: EvidenceItem[]): CitationView {
  if (!answerText) {
    return {
      answerText,
      citedEvidenceKeys: new Set<string>(),
      citationByEvidenceKey: new Map<string, number>(),
      citationKeyByNumber: new Map<number, string>(),
    };
  }

  const citedEvidenceKeys = new Set<string>();
  const citationByEvidenceKey = new Map<string, number>();
  const citationKeyByNumber = new Map<number, string>();
  let nextCitationNumber = 1;

  const normalizedAnswer = answerText.replace(CITATION_PATTERN, (fullMatch, content: string) => {
    const evidenceIndex = resolveCitationToEvidenceIndex(content, evidence);
    if (evidenceIndex === null) return fullMatch;

    const item = evidence[evidenceIndex];
    if (!item) return fullMatch;

    const key = evidenceKey(item);
    citedEvidenceKeys.add(key);

    if (!citationByEvidenceKey.has(key)) {
      citationByEvidenceKey.set(key, nextCitationNumber);
      citationKeyByNumber.set(nextCitationNumber, key);
      nextCitationNumber += 1;
    }

    return `[${citationByEvidenceKey.get(key)}]`;
  });

  return {
    answerText: normalizedAnswer,
    citedEvidenceKeys,
    citationByEvidenceKey,
    citationKeyByNumber,
  };
}

function renderAnswerWithCitations(
  answerText: string,
  citationKeyByNumber: Map<number, string>,
  onCitationClick: (evidenceKey: string) => void,
): ReactNode[] {
  const output: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  NUMBERED_CITATION_PATTERN.lastIndex = 0;

  while ((match = NUMBERED_CITATION_PATTERN.exec(answerText)) !== null) {
    if (match.index > cursor) {
      output.push(answerText.slice(cursor, match.index));
    }
    const citationNumber = Number(match[1]);
    const evidenceTarget = citationKeyByNumber.get(citationNumber);
    if (evidenceTarget) {
      output.push(
        <button
          key={`citation-${match.index}-${citationNumber}`}
          type="button"
          className="citation-inline"
          onClick={() => onCitationClick(evidenceTarget)}
        >
          [{citationNumber}]
        </button>,
      );
    } else {
      output.push(match[0]);
    }
    cursor = match.index + match[0].length;
  }

  if (cursor < answerText.length) {
    output.push(answerText.slice(cursor));
  }
  return output;
}

function formatQuestionType(questionType: string | null): string {
  if (!questionType) return "Unclassified";

  return questionType
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((word) => (word ? `${word[0].toUpperCase()}${word.slice(1)}` : word))
    .join(" ");
}

function formatComplianceStatus(status: Session["confidence"]["compliance_status"]): string {
  return status
    .replace(/_/g, " ")
    .split(" ")
    .map((word) => (word ? `${word[0].toUpperCase()}${word.slice(1)}` : word))
    .join(" ");
}

function formatDraftState(status: AnswerVersion["status"]): string {
  return status
    .replace(/_/g, " ")
    .split(" ")
    .map((word) => (word ? `${word[0].toUpperCase()}${word.slice(1)}` : word))
    .join(" ");
}

function formatRetrievalMethod(method: string): string {
  switch (normalizeToken(method)) {
    case "semantic":
      return "Semantic match";
    case "keyword":
      return "Keyword match";
    default:
      return method ? `${method[0].toUpperCase()}${method.slice(1)}` : "Unknown method";
  }
}

function formatDraftTimestamp(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return timestamp;
  return parsed.toLocaleString();
}

type DisclosurePanelProps = {
  title: string;
  summary: string;
  expanded: boolean;
  onToggle: () => void;
  showLabel: string;
  hideLabel: string;
  tone?: "default" | "caution";
  children: ReactNode;
};

function DisclosurePanel({
  title,
  summary,
  expanded,
  onToggle,
  showLabel,
  hideLabel,
  tone = "default",
  children,
}: DisclosurePanelProps) {
  return (
    <section className={`disclosure-card${tone === "caution" ? " disclosure-card-caution" : ""}`}>
      <div className="disclosure-header">
        <div>
          <h3>{title}</h3>
          <p className="disclosure-summary-line">{summary}</p>
        </div>
        <button type="button" className="secondary disclosure-trigger" onClick={onToggle} aria-expanded={expanded}>
          {expanded ? hideLabel : showLabel}
        </button>
      </div>
      <div className={`disclosure-panel${expanded ? " open" : ""}`}>
        <div className="disclosure-panel-inner">{children}</div>
      </div>
    </section>
  );
}

export function WorkflowShell() {
  const [question, setQuestion] = useState("");
  const [tone, setTone] = useState<Tone>("formal");
  const [feedback, setFeedback] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [drafts, setDrafts] = useState<AnswerVersion[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [compareEnabled, setCompareEnabled] = useState(false);
  const [compareDraftId, setCompareDraftId] = useState<string>("");
  const [compareSegments, setCompareSegments] = useState<DraftDiffSegment[]>([]);
  const [loading, setLoading] = useState(false);
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false);
  const [isSubmittingRevision, setIsSubmittingRevision] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<string | null>(null);
  const [revisionProgress, setRevisionProgress] = useState<string | null>(null);
  const [reviewMode, setReviewMode] = useState<"none" | "revise">("none");
  const [isReviewSummaryExpanded, setIsReviewSummaryExpanded] = useState(false);
  const [isEvidenceGapsExpanded, setIsEvidenceGapsExpanded] = useState(false);
  const [isRevisionHistoryExpanded, setIsRevisionHistoryExpanded] = useState(false);
  const [excludedEvidenceKeys, setExcludedEvidenceKeys] = useState<Set<string>>(new Set<string>());
  const [activeEvidenceKey, setActiveEvidenceKey] = useState<string | null>(null);
  const [reviewedEvidenceGaps, setReviewedEvidenceGaps] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const evidenceRefMap = useRef<Map<string, HTMLDivElement | null>>(new Map<string, HTMLDivElement | null>());

  const canSubmit = question.trim().length >= 10 && !loading;
  const isApproved = session?.status === "approved";
  const confidenceScore = session?.confidence?.score ?? null;
  const evidenceGapCount = session?.evidence_gap_count ?? session?.confidence?.evidence_gaps?.length ?? 0;
  const hasEvidenceGaps = evidenceGapCount > 0;
  const requiresGapAcknowledgement = session?.requires_gap_acknowledgement ?? hasEvidenceGaps;
  const isGapAcknowledged = !requiresGapAcknowledgement || reviewedEvidenceGaps;
  const approveWarning = confidenceScore !== null && confidenceScore < CONFIDENCE_WARNING_THRESHOLD;
  const currentDraft = useMemo(
    () => drafts.find((draft) => draft.is_current) ?? drafts[drafts.length - 1] ?? null,
    [drafts],
  );
  const selectedDraft = useMemo(() => {
    if (!drafts.length) return null;
    if (selectedDraftId) {
      const found = drafts.find((draft) => draft.version_id === selectedDraftId);
      if (found) return found;
    }
    return currentDraft;
  }, [drafts, selectedDraftId, currentDraft]);
  const compareTargetDraft = useMemo(
    () => drafts.find((draft) => draft.version_id === compareDraftId) ?? null,
    [drafts, compareDraftId],
  );
  const isCompareMode = compareEnabled && !!selectedDraft && !!compareTargetDraft;
  const canApprove =
    !loading &&
    isGapAcknowledged &&
    (!selectedDraft || (selectedDraft.is_current && !isCompareMode));
  const isViewingCurrentDraft = selectedDraft ? selectedDraft.is_current : true;
  const isViewingHistoricalDraft = selectedDraft ? !selectedDraft.is_current : false;
  const canUseWorkflowActions = !isApproved && isViewingCurrentDraft && !isCompareMode;
  const viewingLabel = selectedDraft
    ? `Draft ${selectedDraft.version_number}${selectedDraft.is_current ? " (current)" : ""}`
    : isApproved
      ? "Final Response (locked)"
      : "Current draft";
  const displayedExcludedEvidenceKeys = useMemo(
    () =>
      selectedDraft && !selectedDraft.is_current
        ? new Set(selectedDraft.excluded_chunk_ids)
        : excludedEvidenceKeys,
    [selectedDraft?.version_id, selectedDraft?.is_current, selectedDraft?.excluded_chunk_ids, excludedEvidenceKeys],
  );
  const displayedAnswerText = selectedDraft?.content ?? session?.final_answer ?? session?.draft_answer ?? "";
  const citationView = useMemo(
    () => buildCitationView(displayedAnswerText, session?.evidence ?? []),
    [displayedAnswerText, session?.evidence],
  );
  const citationCount = citationView.citedEvidenceKeys.size;
  const latestSnapshotTimestamp = currentDraft?.created_at ?? session?.updated_at ?? null;
  const approvalTimestamp = session?.approved_at ?? null;
  const finalVersionNumber = session?.final_version_number ?? currentDraft?.version_number ?? null;
  const reviewerLabel = session?.reviewer_id ?? "Unassigned";
  const selectedVersionLabel = selectedDraft
    ? `Draft ${selectedDraft.version_number}`
    : finalVersionNumber
      ? `Draft ${finalVersionNumber}`
      : "N/A";
  const selectedVersionStatus = selectedDraft ? formatDraftState(selectedDraft.status) : statusLabel(session?.status ?? "draft");
  const complianceSummary = session ? formatComplianceStatus(session.confidence.compliance_status) : "Unknown";
  const approveButtonLabel = !isGapAcknowledged
    ? "Approve (review required)"
    : approveWarning
      ? "Approve (Low Confidence)"
      : "Approve";

  const timelineText = useMemo(() => {
    if (!session) return "Submit a question to begin the workflow.";
    if (session.status === "approved") return "Final answer approved and locked.";
    if (session.status === "awaiting_review") return "Draft generated. Reviewer decision required.";
    if (session.status === "revision_requested") return "Revision requested. Submit feedback to continue.";
    return "Workflow running.";
  }, [session]);

  useEffect(() => {
    if (!session) {
      setDrafts([]);
      setSelectedDraftId(null);
      setCompareEnabled(false);
      setCompareDraftId("");
      setCompareSegments([]);
      setIsReviewSummaryExpanded(false);
      setIsEvidenceGapsExpanded(false);
      setIsRevisionHistoryExpanded(false);
      setExcludedEvidenceKeys(new Set<string>());
      setReviewedEvidenceGaps(false);
      setActiveEvidenceKey(null);
      return;
    }
    const nextExcluded = new Set<string>();
    for (const item of session.evidence ?? []) {
      if (item.excluded_by_reviewer) {
        nextExcluded.add(evidenceKey(item));
      }
    }
    setExcludedEvidenceKeys(nextExcluded);
    const requiresAck = session.requires_gap_acknowledgement ?? !!session.confidence?.evidence_gaps?.length;
    setReviewedEvidenceGaps(!requiresAck || session.evidence_gaps_acknowledged);
    setIsEvidenceGapsExpanded(requiresAck);
    setActiveEvidenceKey(null);

    let cancelled = false;
    const hydrateDrafts = async () => {
      try {
        const fetched = await fetchDrafts(session.id);
        if (cancelled) return;
        setDrafts(fetched);
      } catch {
        if (cancelled) return;
        setDrafts(session.answer_versions ?? []);
      }
    };
    void hydrateDrafts();

    return () => {
      cancelled = true;
    };
  }, [session?.id, session?.updated_at]);

  useEffect(() => {
    if (!drafts.length) {
      setSelectedDraftId(null);
      setCompareEnabled(false);
      setCompareDraftId("");
      return;
    }

    const hasSelected = selectedDraftId ? drafts.some((draft) => draft.version_id === selectedDraftId) : false;
    if (!hasSelected) {
      const latest = drafts.find((draft) => draft.is_current) ?? drafts[drafts.length - 1];
      setSelectedDraftId(latest?.version_id ?? null);
    }

    if (compareDraftId && !drafts.some((draft) => draft.version_id === compareDraftId)) {
      setCompareDraftId("");
      setCompareEnabled(false);
    }
  }, [drafts, selectedDraftId, compareDraftId]);

  useEffect(() => {
    if (!compareEnabled) {
      setCompareSegments([]);
      return;
    }

    if (!session || !selectedDraft) {
      setCompareSegments([]);
      return;
    }

    let targetId = compareDraftId;
    if (!targetId) {
      const previous = [...drafts]
        .filter((draft) => draft.version_number < selectedDraft.version_number)
        .sort((a, b) => b.version_number - a.version_number)[0];
      targetId = previous?.version_id ?? "";
      if (targetId) {
        setCompareDraftId(targetId);
      } else {
        setCompareEnabled(false);
        setCompareSegments([]);
        return;
      }
    }

    if (targetId === selectedDraft.version_id) {
      setCompareSegments([]);
      return;
    }

    let cancelled = false;
    const loadComparison = async () => {
      try {
        const comparison = await compareDrafts(session.id, targetId, selectedDraft.version_id);
        if (cancelled) return;
        setCompareSegments(comparison.segments);
      } catch {
        if (cancelled) return;
        setCompareSegments([]);
      }
    };
    void loadComparison();
    return () => {
      cancelled = true;
    };
  }, [compareEnabled, compareDraftId, drafts, selectedDraft?.version_id, selectedDraft?.version_number, session?.id]);

  useEffect(() => {
    if (!canUseWorkflowActions && reviewMode === "revise") {
      setReviewMode("none");
    }
  }, [canUseWorkflowActions, reviewMode]);

  function registerEvidenceCardRef(key: string, node: HTMLDivElement | null) {
    evidenceRefMap.current.set(key, node);
  }

  function focusEvidenceCard(key: string) {
    setActiveEvidenceKey(key);
    evidenceRefMap.current.get(key)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function toggleEvidenceExclusion(key: string) {
    setExcludedEvidenceKeys((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleRevisionMode() {
    if (reviewMode === "revise") {
      setReviewMode("none");
      return;
    }
    setReviewMode("revise");
    if (requiresGapAcknowledgement) {
      setIsEvidenceGapsExpanded(true);
    }
  }

  async function submitQuestion() {
    if (!canSubmit) return;
    setLoading(true);
    setIsGeneratingDraft(true);
    setGenerationProgress("Initializing workflow...");
    setRevisionProgress(null);
    setError(null);
    setReviewMode("none");
    setIsReviewSummaryExpanded(false);
    setIsEvidenceGapsExpanded(false);
    setIsRevisionHistoryExpanded(false);
    setFeedback("");
    setExcludedEvidenceKeys(new Set<string>());
    setReviewedEvidenceGaps(false);
    setActiveEvidenceKey(null);
    setDrafts([]);
    setSelectedDraftId(null);
    setCompareEnabled(false);
    setCompareDraftId("");
    setCompareSegments([]);

    const threadId = crypto.randomUUID();
    let pollActive = true;
    const pollProgress = async () => {
      try {
        const liveSession = await fetchSessionByThreadId(threadId);
        if (!pollActive || !liveSession) return;
        setSession(liveSession);
        setGenerationProgress(nodeProgressLabel(liveSession));
      } catch {
        // Best-effort polling while ask request is still in flight.
      }
    };
    await pollProgress();
    const pollTimer = window.setInterval(() => {
      void pollProgress();
    }, 900);

    try {
      const next = await askQuestion(question.trim(), tone, threadId);
      setSession(next);
      setGenerationProgress(nodeProgressLabel(next));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit question.");
      setGenerationProgress(null);
    } finally {
      pollActive = false;
      window.clearInterval(pollTimer);
      setIsGeneratingDraft(false);
      setLoading(false);
    }
  }

  async function approveDraft() {
    if (!session || loading) return;
    if (selectedDraft && !selectedDraft.is_current) {
      setError("Viewing historical draft. Approve applies only to the current draft.");
      return;
    }
    if (isCompareMode) {
      setError("Comparison mode is read-only. Exit compare mode to approve the current draft.");
      return;
    }
    if (requiresGapAcknowledgement && !isGapAcknowledged) {
      setIsReviewSummaryExpanded(true);
      setIsEvidenceGapsExpanded(true);
      setError("Review and acknowledge evidence gaps before approval.");
      return;
    }
    if (approveWarning) {
      const proceed = window.confirm(
        `Confidence is ${confidenceScore?.toFixed(2)} (< ${CONFIDENCE_WARNING_THRESHOLD.toFixed(2)}). Approve anyway?`,
      );
      if (!proceed) return;
    }

    setLoading(true);
    setError(null);

    try {
      const next = await reviewSession(session.id, "approve", {
        evidenceGapsAcknowledged: isGapAcknowledged,
      });
      setSession(next);
      setReviewMode("none");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve draft.");
    } finally {
      setLoading(false);
    }
  }

  async function submitRevision() {
    if (!session || loading) return;
    if (selectedDraft && !selectedDraft.is_current) {
      setError("Viewing historical draft. Submit Revision applies only to the current draft.");
      return;
    }
    if (isCompareMode) {
      setError("Comparison mode is read-only. Exit compare mode to submit a revision.");
      return;
    }
    if (!feedback.trim() && excludedEvidenceKeys.size === 0) {
      setError("Add revision feedback or exclude a citation chunk before submitting.");
      return;
    }

    const activeSessionId = session.id;
    setLoading(true);
    setIsSubmittingRevision(true);
    setRevisionProgress("Initializing workflow...");
    setError(null);

    let pollActive = true;
    const pollProgress = async () => {
      try {
        const liveSession = await fetchSession(activeSessionId);
        if (!pollActive || !liveSession) return;
        setSession(liveSession);
        setRevisionProgress(nodeProgressLabel(liveSession));
      } catch {
        // Best-effort polling while revision request is in flight.
      }
    };
    await pollProgress();
    const pollTimer = window.setInterval(() => {
      void pollProgress();
    }, 900);

    try {
      const next = await reviewSession(activeSessionId, "revise", {
        reviewComments: feedback.trim() || undefined,
        excludedEvidenceKeys: Array.from(excludedEvidenceKeys),
        evidenceGapsAcknowledged: isGapAcknowledged,
      });
      setSession(next);
      // After a successful redraft, keep the UI pinned to the latest current draft
      // so reviewer actions remain available without manual version reselection.
      setSelectedDraftId(null);
      setCompareEnabled(false);
      setCompareDraftId("");
      setCompareSegments([]);
      setRevisionProgress(nodeProgressLabel(next));
      setFeedback("");
      setReviewMode("none");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to request revision.");
      setRevisionProgress(null);
    } finally {
      pollActive = false;
      window.clearInterval(pollTimer);
      setIsSubmittingRevision(false);
      setLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="backdrop-grid" />
      <header className="page-header">
        <div className="brand-row">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <path
                d="M12 2.5 20 7v10l-8 4.5L4 17V7l8-4.5Zm0 3.1L6.7 8.6v6.8l5.3 3 5.3-3V8.6L12 5.6Zm-3 7.1h5.2a1.8 1.8 0 1 0 0-3.6H9v1.8h5.1a.5.5 0 0 1 0 1H9v1.8Z"
                fill="currentColor"
              />
            </svg>
          </span>
          <h1>RespondAI</h1>
        </div>
        <p className="page-tagline">Draft, review, and approve investor-grade RFP/DDQ responses with evidence grounding.</p>
      </header>

      <section className="workflow-grid">
        <article className="glass-panel left-panel">
          <h2>Question Intake</h2>
          <p className="panel-subtitle">Capture the RFP prompt and desired response style.</p>

          <label className="field-label" htmlFor="question">
            RFP Question
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={8}
            placeholder="Enter an investor due diligence question..."
          />

          <label className="field-label" htmlFor="tone">
            Tone
          </label>
          <select id="tone" value={tone} onChange={(event) => setTone(event.target.value as Tone)}>
            <option value="formal">Formal investor tone</option>
            <option value="concise">Concise</option>
            <option value="detailed">Detailed</option>
          </select>

          <div className="actions-row">
            <button onClick={submitQuestion} disabled={!canSubmit}>
              {isGeneratingDraft && loading ? "Running workflow..." : "Generate Draft"}
            </button>
            {isGeneratingDraft && loading && (
              <span className="inline-progress" aria-live="polite">
                {generationProgress || "Initializing workflow..."}
              </span>
            )}
          </div>

          <div className="sample-prompts">
            <p>Sample prompts</p>
            {SAMPLE_QUESTIONS.map((sample) => (
              <button key={sample} type="button" className="sample-pill" onClick={() => setQuestion(sample)}>
                {sample}
              </button>
            ))}
          </div>
        </article>

        <article className="glass-panel middle-panel">
          <div className="panel-heading-row">
            <h2>Draft & Review</h2>
            <span className="status-chip">{session ? statusLabel(session.status) : "Idle"}</span>
          </div>

          <p className="workflow-summary-text">{workflowSummary(session?.status ?? null)}</p>
          {session && <p className="panel-subtitle middle-panel-timeline">{timelineText}</p>}

          {!session && <p className="placeholder">No session yet. Submit a question to start the graph.</p>}

          {session && (
            <>
              <div className="draft-primary-card">
                <div className="answer-heading-row">
                  <h3>{isApproved ? "Final Response (locked)" : "Draft Response"}</h3>
                  <span className="question-type-chip">Question type: {formatQuestionType(session.question_type)}</span>
                </div>
                <p className="version-meta">Viewing: {viewingLabel}</p>
                <p className="version-meta">
                  Version: {selectedVersionLabel} ·{" "}
                  {selectedDraft
                    ? formatDraftTimestamp(selectedDraft.created_at)
                    : latestSnapshotTimestamp
                      ? formatDraftTimestamp(latestSnapshotTimestamp)
                      : "N/A"}
                </p>
                <p className="version-meta">
                  Status: {statusLabel(session.status)} · View state: {selectedVersionStatus}
                </p>
                {isCompareMode && <p className="version-meta">Compare with: {compareTargetDraft?.label ?? "Off"}</p>}
                {!!selectedDraft?.revision_feedback && (
                  <p className="draft-feedback-note">Revision feedback: {selectedDraft.revision_feedback}</p>
                )}
                <p className="answer-with-citations">
                  {citationView.answerText
                    ? renderAnswerWithCitations(citationView.answerText, citationView.citationKeyByNumber, focusEvidenceCard)
                    : "No answer generated yet."}
                </p>
              </div>

              <div className="version-history-block">
                <DisclosurePanel
                  title="Review summary"
                  summary={`Confidence: ${
                    confidenceScore !== null ? confidenceScore.toFixed(2) : "N/A"
                  } · Compliance: ${complianceSummary} · ${evidenceGapCount} evidence gap${
                    evidenceGapCount === 1 ? "" : "s"
                  } · ${citationCount} citation${citationCount === 1 ? "" : "s"}`}
                  expanded={isReviewSummaryExpanded}
                  onToggle={() => setIsReviewSummaryExpanded((current) => !current)}
                  showLabel="View details"
                  hideLabel="Hide details"
                >
                  <p>{session.confidence_notes || "No confidence notes available."}</p>
                  <div className="confidence-summary-row">
                    <span>
                      Heuristic confidence: {session.confidence.score !== null ? session.confidence.score.toFixed(2) : "N/A"}
                    </span>
                    <span>Compliance: {complianceSummary}</span>
                    <span>
                      Evidence coverage: {citationCount}/{session.evidence.length} cited chunks
                    </span>
                    {session.confidence.retrieval_strategy ? (
                      <span>Retrieval strategy: {session.confidence.retrieval_strategy}</span>
                    ) : null}
                    {session.confidence.coverage && session.confidence.coverage !== "unknown" ? (
                      <span>Evaluator coverage: {session.confidence.coverage}</span>
                    ) : null}
                  </div>
                  <div className="review-notes-block">
                    <p>
                      <strong>Model notes:</strong> {session.confidence.model_notes || "No model notes provided."}
                    </p>
                    <p>
                      <strong>Retrieval notes:</strong> {session.confidence.retrieval_notes || "No retrieval notes provided."}
                    </p>
                    {session.confidence.recommended_action && session.confidence.recommended_action !== "unknown" ? (
                      <p>
                        <strong>Evaluator recommendation:</strong> {session.confidence.recommended_action}
                      </p>
                    ) : null}
                  </div>
                </DisclosurePanel>

                {hasEvidenceGaps ? (
                  <DisclosurePanel
                    title="Evidence gaps"
                    summary={`${evidenceGapCount} evidence gap${evidenceGapCount === 1 ? "" : "s"} · ${
                      reviewedEvidenceGaps ? "Acknowledged" : "Needs review"
                    }`}
                    expanded={isEvidenceGapsExpanded}
                    onToggle={() => setIsEvidenceGapsExpanded((current) => !current)}
                    showLabel="Review"
                    hideLabel="Collapse"
                    tone="caution"
                  >
                    <div className="gaps-checklist">
                      <ul>
                        {session.confidence.evidence_gaps.map((gap) => (
                          <li key={gap}>{gap}</li>
                        ))}
                      </ul>
                      {!isApproved && (
                        <label className="gap-ack">
                          <input
                            type="checkbox"
                            checked={reviewedEvidenceGaps}
                            onChange={(event) => setReviewedEvidenceGaps(event.target.checked)}
                          />
                          I have reviewed these evidence gaps and accept the remaining uncertainty.
                        </label>
                      )}
                    </div>
                  </DisclosurePanel>
                ) : (
                  <section className="disclosure-card disclosure-card-success">
                    <div className="disclosure-header disclosure-header-static">
                      <div>
                        <h3>Evidence gaps</h3>
                        <p className="disclosure-summary-line">No outstanding evidence gaps.</p>
                      </div>
                      <span className="success-chip">Clear</span>
                    </div>
                  </section>
                )}

                {canUseWorkflowActions && (
                  <div className="review-actions action-bar">
                    <button
                      onClick={approveDraft}
                      disabled={!canApprove}
                      className={approveWarning && isGapAcknowledged ? "warning" : ""}
                      title={
                        approveWarning && isGapAcknowledged
                          ? `Low confidence (${confidenceScore?.toFixed(2)}). Approval requires confirmation.`
                          : undefined
                      }
                    >
                      {approveButtonLabel}
                    </button>
                    <button onClick={toggleRevisionMode} disabled={loading} className="secondary">
                      {reviewMode === "revise" ? "Cancel Revision" : "Revise"}
                    </button>
                  </div>
                )}

                {isApproved && (
                  <div className="approved-action-summary">
                    <span>Decision: Approved (locked)</span>
                    <span>Final version: {finalVersionNumber ? `Draft ${finalVersionNumber}` : "N/A"}</span>
                    <span>Approved at: {approvalTimestamp ? formatDraftTimestamp(approvalTimestamp) : "N/A"}</span>
                    <span>Reviewer: {reviewerLabel}</span>
                    <span>
                      Evidence gaps acknowledged:{" "}
                      {session.requires_gap_acknowledgement
                        ? session.evidence_gaps_acknowledged
                          ? "Yes"
                          : "No"
                        : "Not required"}
                    </span>
                    <span>
                      Acknowledged at:{" "}
                      {session.evidence_gaps_acknowledged_at
                        ? formatDraftTimestamp(session.evidence_gaps_acknowledged_at)
                        : "N/A"}
                    </span>
                  </div>
                )}

                <DisclosurePanel
                  title="Revision history"
                  summary={
                    drafts.length
                      ? `${drafts.length} draft version${drafts.length === 1 ? "" : "s"} · latest snapshot ${
                          latestSnapshotTimestamp ? formatDraftTimestamp(latestSnapshotTimestamp) : "N/A"
                        }`
                      : "No draft versions yet."
                  }
                  expanded={isRevisionHistoryExpanded}
                  onToggle={() => setIsRevisionHistoryExpanded((current) => !current)}
                  showLabel="View history"
                  hideLabel="Hide history"
                >
                  {!drafts.length && <p className="placeholder">Draft history will appear after the first draft is generated.</p>}
                  {!!drafts.length && (
                    <>
                      <div className="version-compare-row">
                        <span>Viewing:</span>
                        <select
                          value={selectedDraft?.version_id ?? ""}
                          onChange={(event) => setSelectedDraftId(event.target.value || null)}
                        >
                          {drafts.map((draft) => (
                            <option key={draft.version_id} value={draft.version_id}>
                              {draft.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="version-compare-row">
                        <span>Compare with:</span>
                        <select
                          value={compareEnabled ? compareDraftId : ""}
                          onChange={(event) => {
                            const nextValue = event.target.value;
                            if (!nextValue) {
                              setCompareEnabled(false);
                              setCompareDraftId("");
                              setCompareSegments([]);
                              return;
                            }
                            setCompareEnabled(true);
                            setCompareDraftId(nextValue);
                          }}
                        >
                          <option value="">Off</option>
                          {drafts
                            .filter((draft) => draft.version_id !== selectedDraft?.version_id)
                            .map((draft) => (
                              <option key={draft.version_id} value={draft.version_id}>
                                {draft.label}
                              </option>
                            ))}
                        </select>
                      </div>
                      {(isViewingHistoricalDraft || isCompareMode) && (
                        <p className="history-note">
                          {isCompareMode
                            ? "Comparison mode is read-only. Workflow actions apply only to the current latest draft."
                            : "Viewing historical draft. Workflow actions apply only to the current latest draft."}
                        </p>
                      )}
                      {isCompareMode && (
                        <div className="diff-view" aria-live="polite">
                          <p className="version-meta">
                            Diff: {compareTargetDraft?.label ?? "Draft"} vs {selectedDraft?.label ?? "Draft"}
                          </p>
                          {compareSegments.length ? (
                            compareSegments.map((segment, index) => (
                              <span key={`${segment.kind}-${index}-${segment.text}`} className={`diff-token diff-token-${segment.kind}`}>
                                {segment.text}
                              </span>
                            ))
                          ) : (
                            <span className="diff-token diff-token-same">No differences available for this pair.</span>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </DisclosurePanel>

                {reviewMode === "revise" && canUseWorkflowActions && (
                  <div className="revision-box">
                    <h3>Revision request</h3>
                    <label className="field-label" htmlFor="feedback">
                      Feedback
                    </label>
                    <textarea
                      id="feedback"
                      rows={4}
                      value={feedback}
                      onChange={(event) => setFeedback(event.target.value)}
                      placeholder="Describe what should change in the draft."
                    />
                    {!!excludedEvidenceKeys.size && (
                      <p className="revision-exclusion-note">
                        {excludedEvidenceKeys.size} citation chunk(s) will be excluded from this redraft.
                      </p>
                    )}
                    <div className="actions-row revision-submit-row">
                      <button onClick={submitRevision} disabled={loading}>
                        Submit Revision
                      </button>
                      {isSubmittingRevision && loading && (
                        <span className="inline-progress" aria-live="polite">
                          {revisionProgress || "Updating revision..."}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {error && <p className="error-text">{error}</p>}
        </article>

        <article className="glass-panel right-panel">
          <h2>Evidence & Citations</h2>
          <p className="panel-subtitle">Retrieved supporting chunks used to draft the response.</p>

          {!session?.evidence.length && <p className="placeholder">Evidence will appear after retrieval.</p>}

          {session?.evidence.map((item) => {
            const key = evidenceKey(item);
            const citationNumber = citationView.citationByEvidenceKey.get(key);
            const isCitedChunk = citationView.citedEvidenceKeys.has(key);
            const isExcluded = displayedExcludedEvidenceKeys.has(key);
            const isFocused = activeEvidenceKey === key;
            const badgeLabel = citationNumber
              ? `[${citationNumber}]`
              : isExcluded
                ? "Excluded from revision"
                : isApproved
                  ? "Not used in final answer"
                  : isViewingHistoricalDraft
                    ? "Not used in selected draft"
                    : "Not used in current draft";

            return (
              <div
                key={item.chunk_id}
                ref={(node) => registerEvidenceCardRef(key, node)}
                className={`evidence-card${isCitedChunk ? " evidence-card-cited" : " evidence-card-uncited"}${
                  isExcluded ? " evidence-card-excluded" : ""
                }${isFocused ? " evidence-card-focused" : ""}`}
              >
                <div className="evidence-title-row">
                  <span className={`citation-badge${isCitedChunk ? " cited" : " uncited"}`}>
                    {badgeLabel}
                  </span>
                  <span className="evidence-document">{item.document_filename}</span>
                </div>
                <p>{item.text}</p>
                <div className="evidence-detail-row">
                  <span>
                    Chunk {item.chunk_index} · {formatRetrievalMethod(item.retrieval_method)} · Score:{" "}
                    {item.score.toFixed(2)}
                  </span>
                </div>
                {canUseWorkflowActions && (
                  <div className="evidence-footer">
                    <button
                      type="button"
                      className={`source-toggle${isExcluded ? " active" : ""}`}
                      onClick={() => toggleEvidenceExclusion(key)}
                      disabled={loading}
                    >
                      {isExcluded ? "Include in next revision" : "Exclude in next revision"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </article>
      </section>
    </main>
  );
}
