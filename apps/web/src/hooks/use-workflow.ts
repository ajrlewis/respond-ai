import { useEffect, useMemo, useState } from "react";

import {
  askQuestion,
  fetchSession,
  fetchSessionByThreadId,
  reviewSession,
  type AnswerVersion,
  type Session,
  type Tone,
} from "@/lib/api";
import {
  CONFIDENCE_WARNING_THRESHOLD,
  buildTimelineText,
  evidenceKey,
  nodeProgressLabel,
} from "@/lib/workflow";

export type ReviewMode = "none" | "revise";

type ApproveContext = {
  selectedDraft: AnswerVersion | null;
  isCompareMode: boolean;
};

type SubmitRevisionContext = {
  selectedDraft: AnswerVersion | null;
  isCompareMode: boolean;
  onSuccess?: () => void;
};

type GenerateDraftContext = {
  onBeforeStart?: () => void;
};

type UseWorkflowResult = {
  question: string;
  tone: Tone;
  feedback: string;
  session: Session | null;
  loading: boolean;
  isGeneratingDraft: boolean;
  isSubmittingRevision: boolean;
  generationProgress: string | null;
  revisionProgress: string | null;
  reviewMode: ReviewMode;
  excludedEvidenceKeys: Set<string>;
  reviewedEvidenceGaps: boolean;
  error: string | null;
  isReviewSummaryExpanded: boolean;
  isEvidenceGapsExpanded: boolean;
  isRevisionHistoryExpanded: boolean;
  canSubmit: boolean;
  isApproved: boolean;
  confidenceScore: number | null;
  evidenceGapCount: number;
  hasEvidenceGaps: boolean;
  requiresGapAcknowledgement: boolean;
  isGapAcknowledged: boolean;
  approveWarning: boolean;
  timelineText: string;
  setQuestion: (value: string) => void;
  setTone: (value: Tone) => void;
  setFeedback: (value: string) => void;
  setReviewedEvidenceGaps: (value: boolean) => void;
  setIsReviewSummaryExpanded: (value: boolean) => void;
  setIsEvidenceGapsExpanded: (value: boolean) => void;
  setIsRevisionHistoryExpanded: (value: boolean) => void;
  handleGenerateDraft: (context?: GenerateDraftContext) => Promise<void>;
  handleApprove: (context: ApproveContext) => Promise<void>;
  handleToggleRevisionMode: (canUseWorkflowActions: boolean) => void;
  handleCancelRevision: () => void;
  handleSubmitRevision: (context: SubmitRevisionContext) => Promise<void>;
  toggleEvidenceExclusion: (key: string) => void;
};

export function useWorkflow(reviewerId?: string): UseWorkflowResult {
  const [question, setQuestion] = useState("");
  const [tone, setTone] = useState<Tone>("formal");
  const [feedback, setFeedback] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false);
  const [isSubmittingRevision, setIsSubmittingRevision] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<string | null>(null);
  const [revisionProgress, setRevisionProgress] = useState<string | null>(null);
  const [reviewMode, setReviewMode] = useState<ReviewMode>("none");
  const [isReviewSummaryExpanded, setIsReviewSummaryExpanded] = useState(false);
  const [isEvidenceGapsExpanded, setIsEvidenceGapsExpanded] = useState(false);
  const [isRevisionHistoryExpanded, setIsRevisionHistoryExpanded] = useState(false);
  const [excludedEvidenceKeys, setExcludedEvidenceKeys] = useState<Set<string>>(new Set<string>());
  const [reviewedEvidenceGaps, setReviewedEvidenceGaps] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = question.trim().length >= 10 && !loading;
  const isApproved = session?.status === "approved";
  const confidenceScore = session?.confidence?.score ?? null;
  const evidenceGapCount = session?.evidence_gap_count ?? session?.confidence?.evidence_gaps?.length ?? 0;
  const hasEvidenceGaps = evidenceGapCount > 0;
  const requiresGapAcknowledgement = session?.requires_gap_acknowledgement ?? hasEvidenceGaps;
  const isGapAcknowledged = !requiresGapAcknowledgement || reviewedEvidenceGaps;
  const approveWarning = confidenceScore !== null && confidenceScore < CONFIDENCE_WARNING_THRESHOLD;
  const timelineText = useMemo(() => buildTimelineText(session), [session]);

  useEffect(() => {
    if (!session) {
      setExcludedEvidenceKeys(new Set<string>());
      setReviewedEvidenceGaps(false);
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
  }, [session?.id, session?.updated_at]);

  async function handleGenerateDraft(context?: GenerateDraftContext) {
    if (!canSubmit) return;

    context?.onBeforeStart?.();

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

  async function handleApprove(context: ApproveContext) {
    if (!session || loading) return;

    if (context.selectedDraft && !context.selectedDraft.is_current) {
      setError("Viewing historical draft. Approve applies only to the current draft.");
      return;
    }

    if (context.isCompareMode) {
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
        reviewerId: reviewerId?.trim() || undefined,
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

  function handleToggleRevisionMode(canUseWorkflowActions: boolean) {
    if (!canUseWorkflowActions) return;

    if (reviewMode === "revise") {
      setReviewMode("none");
      return;
    }

    setReviewMode("revise");
    if (requiresGapAcknowledgement) {
      setIsEvidenceGapsExpanded(true);
    }
  }

  function handleCancelRevision() {
    setReviewMode("none");
  }

  async function handleSubmitRevision(context: SubmitRevisionContext) {
    if (!session || loading) return;

    if (context.selectedDraft && !context.selectedDraft.is_current) {
      setError("Viewing historical draft. Submit Revision applies only to the current draft.");
      return;
    }

    if (context.isCompareMode) {
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
        reviewerId: reviewerId?.trim() || undefined,
        reviewComments: feedback.trim() || undefined,
        excludedEvidenceKeys: Array.from(excludedEvidenceKeys),
        evidenceGapsAcknowledged: isGapAcknowledged,
      });
      setSession(next);
      setRevisionProgress(nodeProgressLabel(next));
      setFeedback("");
      setReviewMode("none");
      context.onSuccess?.();
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

  function toggleEvidenceExclusion(key: string) {
    setExcludedEvidenceKeys((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return {
    question,
    tone,
    feedback,
    session,
    loading,
    isGeneratingDraft,
    isSubmittingRevision,
    generationProgress,
    revisionProgress,
    reviewMode,
    excludedEvidenceKeys,
    reviewedEvidenceGaps,
    error,
    isReviewSummaryExpanded,
    isEvidenceGapsExpanded,
    isRevisionHistoryExpanded,
    canSubmit,
    isApproved,
    confidenceScore,
    evidenceGapCount,
    hasEvidenceGaps,
    requiresGapAcknowledgement,
    isGapAcknowledged,
    approveWarning,
    timelineText,
    setQuestion,
    setTone,
    setFeedback,
    setReviewedEvidenceGaps,
    setIsReviewSummaryExpanded,
    setIsEvidenceGapsExpanded,
    setIsRevisionHistoryExpanded,
    handleGenerateDraft,
    handleApprove,
    handleToggleRevisionMode,
    handleCancelRevision,
    handleSubmitRevision,
    toggleEvidenceExclusion,
  };
}
