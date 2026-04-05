import { type ReactNode } from "react";

import { type AnswerVersion, type DraftDiffSegment, type Session } from "@/lib/api";
import { formatDraftTimestamp } from "@/lib/format";
import { tokenizeNumberedCitations } from "@/lib/workflow";

import { ActionBar } from "@/components/workflow/action-bar";
import { DraftHeader } from "@/components/workflow/draft-header";
import { EvidenceGaps } from "@/components/workflow/evidence-gaps";
import { RevisionHistory } from "@/components/workflow/revision-history";
import { RevisionRequestPanel } from "@/components/workflow/revision-request-panel";
import { ReviewSummary } from "@/components/workflow/review-summary";
import { StatusBadge } from "@/components/workflow/status-badge";

type DraftPanelProps = {
  session: Session | null;
  workflowSummaryText: string;
  timelineText: string;
  isApproved: boolean;
  workflowStatusLabel: string;
  questionType: string | null;
  viewingLabel: string;
  selectedVersionLabel: string;
  selectedVersionTimestamp: string;
  selectedVersionStatus: string;
  compareLabel: string | null;
  revisionFeedback: string | null;
  answerText: string;
  citationKeyByNumber: Map<number, string>;
  onCitationClick: (evidenceKey: string) => void;
  confidenceScore: number | null;
  complianceSummary: string;
  evidenceGapCount: number;
  citationCount: number;
  confidenceNotes: string | null;
  confidence: Session["confidence"] | null;
  evidenceCount: number;
  isReviewSummaryExpanded: boolean;
  onToggleReviewSummary: () => void;
  hasEvidenceGaps: boolean;
  evidenceGaps: string[];
  reviewedEvidenceGaps: boolean;
  isEvidenceGapsExpanded: boolean;
  onToggleEvidenceGaps: () => void;
  onReviewedEvidenceGapsChange: (checked: boolean) => void;
  canUseWorkflowActions: boolean;
  canApprove: boolean;
  approveWarning: boolean;
  isGapAcknowledged: boolean;
  approveButtonLabel: string;
  reviewMode: "none" | "revise";
  loading: boolean;
  onApprove: () => void;
  onToggleRevision: () => void;
  isRevisionHistoryExpanded: boolean;
  onToggleRevisionHistory: () => void;
  drafts: AnswerVersion[];
  latestSnapshotTimestamp: string | null;
  selectedDraft: AnswerVersion | null;
  selectedDraftId: string | null;
  compareDraftId: string;
  compareEnabled: boolean;
  compareTargetDraft: AnswerVersion | null;
  compareSegments: DraftDiffSegment[];
  isViewingHistoricalDraft: boolean;
  isCompareMode: boolean;
  onSelectDraft: (draftId: string | null) => void;
  onSelectCompareDraft: (draftId: string) => void;
  feedback: string;
  excludedEvidenceCount: number;
  isSubmittingRevision: boolean;
  revisionProgress: string | null;
  onFeedbackChange: (feedback: string) => void;
  onSubmitRevision: () => void;
  finalVersionNumber: number | null;
  approvalTimestamp: string | null;
  reviewerLabel: string;
  requiresGapAcknowledgement: boolean;
  evidenceGapsAcknowledged: boolean;
  evidenceGapsAcknowledgedAt: string | null;
  error: string | null;
};

function renderAnswerWithCitations(
  answerText: string,
  citationKeyByNumber: Map<number, string>,
  onCitationClick: (evidenceKey: string) => void,
): ReactNode[] {
  return tokenizeNumberedCitations(answerText).map((token, index) => {
    if (token.kind === "text") {
      return <span key={`text-${index}`}>{token.value}</span>;
    }

    const evidenceTarget = citationKeyByNumber.get(token.value);
    if (!evidenceTarget) {
      return <span key={`citation-${index}`}>{token.label}</span>;
    }

    return (
      <button
        key={`citation-${index}-${token.value}`}
        type="button"
        className="citation-inline"
        onClick={() => onCitationClick(evidenceTarget)}
      >
        {token.label}
      </button>
    );
  });
}

export function DraftPanel({
  session,
  workflowSummaryText,
  timelineText,
  isApproved,
  workflowStatusLabel,
  questionType,
  viewingLabel,
  selectedVersionLabel,
  selectedVersionTimestamp,
  selectedVersionStatus,
  compareLabel,
  revisionFeedback,
  answerText,
  citationKeyByNumber,
  onCitationClick,
  confidenceScore,
  complianceSummary,
  evidenceGapCount,
  citationCount,
  confidenceNotes,
  confidence,
  evidenceCount,
  isReviewSummaryExpanded,
  onToggleReviewSummary,
  hasEvidenceGaps,
  evidenceGaps,
  reviewedEvidenceGaps,
  isEvidenceGapsExpanded,
  onToggleEvidenceGaps,
  onReviewedEvidenceGapsChange,
  canUseWorkflowActions,
  canApprove,
  approveWarning,
  isGapAcknowledged,
  approveButtonLabel,
  reviewMode,
  loading,
  onApprove,
  onToggleRevision,
  isRevisionHistoryExpanded,
  onToggleRevisionHistory,
  drafts,
  latestSnapshotTimestamp,
  selectedDraft,
  selectedDraftId,
  compareDraftId,
  compareEnabled,
  compareTargetDraft,
  compareSegments,
  isViewingHistoricalDraft,
  isCompareMode,
  onSelectDraft,
  onSelectCompareDraft,
  feedback,
  excludedEvidenceCount,
  isSubmittingRevision,
  revisionProgress,
  onFeedbackChange,
  onSubmitRevision,
  finalVersionNumber,
  approvalTimestamp,
  reviewerLabel,
  requiresGapAcknowledgement,
  evidenceGapsAcknowledged,
  evidenceGapsAcknowledgedAt,
  error,
}: DraftPanelProps) {
  return (
    <article className="glass-panel middle-panel">
      <div className="panel-heading-row">
        <h2>Draft & Review</h2>
        <StatusBadge status={session?.status ?? null} />
      </div>

      <p className="workflow-summary-text">{workflowSummaryText}</p>
      {session ? <p className="panel-subtitle middle-panel-timeline">{timelineText}</p> : null}

      {!session && <p className="placeholder">No session yet. Submit a question to start the graph.</p>}

      {session && (
        <>
          <div className="draft-primary-card">
            <DraftHeader
              isApproved={isApproved}
              questionType={questionType}
              viewingLabel={viewingLabel}
              selectedVersionLabel={selectedVersionLabel}
              selectedVersionTimestamp={selectedVersionTimestamp}
              workflowStatusLabel={workflowStatusLabel}
              selectedVersionStatus={selectedVersionStatus}
              compareLabel={compareLabel}
              revisionFeedback={revisionFeedback}
            />
            <p className="answer-with-citations">
              {answerText
                ? renderAnswerWithCitations(answerText, citationKeyByNumber, onCitationClick)
                : "No answer generated yet."}
            </p>
          </div>

          <div className="version-history-block">
            {confidence ? (
              <ReviewSummary
                confidenceScore={confidenceScore}
                complianceSummary={complianceSummary}
                evidenceGapCount={evidenceGapCount}
                citationCount={citationCount}
                confidenceNotes={confidenceNotes}
                confidence={confidence}
                evidenceCount={evidenceCount}
                expanded={isReviewSummaryExpanded}
                onToggle={onToggleReviewSummary}
              />
            ) : null}

            <EvidenceGaps
              isApproved={isApproved}
              hasEvidenceGaps={hasEvidenceGaps}
              evidenceGapCount={evidenceGapCount}
              evidenceGaps={evidenceGaps}
              reviewedEvidenceGaps={reviewedEvidenceGaps}
              expanded={isEvidenceGapsExpanded}
              onToggle={onToggleEvidenceGaps}
              onReviewedEvidenceGapsChange={onReviewedEvidenceGapsChange}
            />

            <ActionBar
              canUseWorkflowActions={canUseWorkflowActions}
              canApprove={canApprove}
              approveWarning={approveWarning}
              isGapAcknowledged={isGapAcknowledged}
              confidenceScore={confidenceScore}
              approveButtonLabel={approveButtonLabel}
              reviewMode={reviewMode}
              loading={loading}
              onApprove={onApprove}
              onToggleRevision={onToggleRevision}
            />

            {isApproved && (
              <div className="approved-action-summary">
                <span>Decision: Approved (locked)</span>
                <span>Final version: {finalVersionNumber ? `Draft ${finalVersionNumber}` : "N/A"}</span>
                <span>Approved at: {approvalTimestamp ? formatDraftTimestamp(approvalTimestamp) : "N/A"}</span>
                <span>Reviewer: {reviewerLabel}</span>
                <span>
                  Evidence gaps acknowledged: {requiresGapAcknowledgement ? (evidenceGapsAcknowledged ? "Yes" : "No") : "Not required"}
                </span>
                <span>
                  Acknowledged at: {evidenceGapsAcknowledgedAt ? formatDraftTimestamp(evidenceGapsAcknowledgedAt) : "N/A"}
                </span>
              </div>
            )}

            <RevisionHistory
              drafts={drafts}
              latestSnapshotTimestamp={latestSnapshotTimestamp}
              selectedDraft={selectedDraft}
              selectedDraftId={selectedDraftId}
              compareDraftId={compareDraftId}
              compareEnabled={compareEnabled}
              compareTargetDraft={compareTargetDraft}
              compareSegments={compareSegments}
              isViewingHistoricalDraft={isViewingHistoricalDraft}
              isCompareMode={isCompareMode}
              expanded={isRevisionHistoryExpanded}
              onToggle={onToggleRevisionHistory}
              onSelectDraft={onSelectDraft}
              onSelectCompareDraft={onSelectCompareDraft}
            />

            {reviewMode === "revise" && canUseWorkflowActions ? (
              <RevisionRequestPanel
                feedback={feedback}
                excludedEvidenceCount={excludedEvidenceCount}
                loading={loading}
                isSubmittingRevision={isSubmittingRevision}
                revisionProgress={revisionProgress}
                onFeedbackChange={onFeedbackChange}
                onSubmitRevision={onSubmitRevision}
              />
            ) : null}
          </div>
        </>
      )}

      {error ? <p className="error-text">{error}</p> : null}
    </article>
  );
}
