"use client";

import { useEffect, useMemo, useState } from "react";

import { DraftPanel } from "@/components/workflow/draft-panel";
import { EvidencePanel } from "@/components/workflow/evidence-panel";
import { QuestionPanel } from "@/components/workflow/question-panel";
import { WorkflowHeader } from "@/components/workflow/workflow-header";
import { useDraftHistory } from "@/hooks/use-draft-history";
import { useWorkflow } from "@/hooks/use-workflow";
import { formatComplianceStatus, formatDraftState, formatDraftTimestamp } from "@/lib/format";
import { SAMPLE_QUESTIONS, buildCitationView, statusLabel, workflowSummary } from "@/lib/workflow";

type WorkflowShellProps = {
  currentUsername?: string;
  isLoggingOut?: boolean;
  onLogout?: () => void;
};

export function WorkflowShell({ currentUsername, isLoggingOut = false, onLogout }: WorkflowShellProps) {
  const workflow = useWorkflow(currentUsername);
  const draftHistory = useDraftHistory({ session: workflow.session });
  const [activeEvidenceKey, setActiveEvidenceKey] = useState<string | null>(null);

  const displayedExcludedEvidenceKeys = useMemo(
    () =>
      draftHistory.selectedDraft && !draftHistory.selectedDraft.is_current
        ? new Set(draftHistory.selectedDraft.excluded_chunk_ids)
        : workflow.excludedEvidenceKeys,
    [draftHistory.selectedDraft?.version_id, draftHistory.selectedDraft?.is_current, draftHistory.selectedDraft?.excluded_chunk_ids, workflow.excludedEvidenceKeys],
  );

  const displayedAnswerText = draftHistory.selectedDraft?.content ?? workflow.session?.final_answer ?? workflow.session?.draft_answer ?? "";

  const citationView = useMemo(
    () => buildCitationView(displayedAnswerText, workflow.session?.evidence ?? []),
    [displayedAnswerText, workflow.session?.evidence],
  );

  const citationCount = citationView.citedEvidenceKeys.size;
  const canUseWorkflowActions = !workflow.isApproved && draftHistory.isViewingCurrentDraft && !draftHistory.isCompareMode;
  const canApprove =
    !workflow.loading &&
    workflow.isGapAcknowledged &&
    (!draftHistory.selectedDraft || (draftHistory.selectedDraft.is_current && !draftHistory.isCompareMode));

  const approveButtonLabel = !workflow.isGapAcknowledged
    ? "Approve (review required)"
    : workflow.approveWarning
      ? "Approve (Low Confidence)"
      : "Approve";

  const finalVersionNumber = workflow.session?.final_version_number ?? draftHistory.currentDraft?.version_number ?? null;
  const selectedVersionLabel = draftHistory.selectedDraft
    ? `Draft ${draftHistory.selectedDraft.version_number}`
    : finalVersionNumber
      ? `Draft ${finalVersionNumber}`
      : "N/A";

  const selectedVersionTimestamp = draftHistory.selectedDraft
    ? formatDraftTimestamp(draftHistory.selectedDraft.created_at)
    : draftHistory.latestSnapshotTimestamp
      ? formatDraftTimestamp(draftHistory.latestSnapshotTimestamp)
      : "N/A";

  const selectedVersionStatus = draftHistory.selectedDraft
    ? formatDraftState(draftHistory.selectedDraft.status)
    : statusLabel(workflow.session?.status ?? "draft");

  const workflowStatusLabel = workflow.session ? statusLabel(workflow.session.status) : "Draft";
  const complianceSummary = workflow.session ? formatComplianceStatus(workflow.session.confidence.compliance_status) : "Unknown";
  const compareLabel = draftHistory.isCompareMode ? draftHistory.compareTargetDraft?.label ?? "Off" : null;

  useEffect(() => {
    if (!canUseWorkflowActions && workflow.reviewMode === "revise") {
      workflow.handleCancelRevision();
    }
  }, [canUseWorkflowActions, workflow.reviewMode, workflow.handleCancelRevision]);

  useEffect(() => {
    setActiveEvidenceKey(null);
  }, [workflow.session?.id, workflow.session?.updated_at]);

  return (
    <main className="page-shell">
      <div className="backdrop-grid" />
      <WorkflowHeader currentUsername={currentUsername} isLoggingOut={isLoggingOut} onLogout={onLogout} />

      <section className="workflow-grid">
        <QuestionPanel
          question={workflow.question}
          tone={workflow.tone}
          canSubmit={workflow.canSubmit}
          isGeneratingDraft={workflow.isGeneratingDraft}
          loading={workflow.loading}
          generationProgress={workflow.generationProgress}
          sampleQuestions={SAMPLE_QUESTIONS}
          onQuestionChange={workflow.setQuestion}
          onToneChange={workflow.setTone}
          onSubmit={() => {
            void workflow.handleGenerateDraft({
              onBeforeStart: () => {
                draftHistory.resetHistory();
                setActiveEvidenceKey(null);
              },
            });
          }}
        />

        <DraftPanel
          session={workflow.session}
          workflowSummaryText={workflowSummary(workflow.session?.status ?? null)}
          timelineText={workflow.timelineText}
          isApproved={workflow.isApproved}
          workflowStatusLabel={workflowStatusLabel}
          questionType={workflow.session?.question_type ?? null}
          viewingLabel={draftHistory.viewingLabel}
          selectedVersionLabel={selectedVersionLabel}
          selectedVersionTimestamp={selectedVersionTimestamp}
          selectedVersionStatus={selectedVersionStatus}
          compareLabel={compareLabel}
          revisionFeedback={draftHistory.selectedDraft?.revision_feedback ?? null}
          answerText={citationView.answerText}
          citationKeyByNumber={citationView.citationKeyByNumber}
          onCitationClick={setActiveEvidenceKey}
          confidenceScore={workflow.confidenceScore}
          complianceSummary={complianceSummary}
          evidenceGapCount={workflow.evidenceGapCount}
          citationCount={citationCount}
          confidenceNotes={workflow.session?.confidence_notes ?? null}
          confidence={workflow.session?.confidence ?? null}
          evidenceCount={workflow.session?.evidence.length ?? 0}
          isReviewSummaryExpanded={workflow.isReviewSummaryExpanded}
          onToggleReviewSummary={() => workflow.setIsReviewSummaryExpanded(!workflow.isReviewSummaryExpanded)}
          hasEvidenceGaps={workflow.hasEvidenceGaps}
          evidenceGaps={workflow.session?.confidence.evidence_gaps ?? []}
          reviewedEvidenceGaps={workflow.reviewedEvidenceGaps}
          isEvidenceGapsExpanded={workflow.isEvidenceGapsExpanded}
          onToggleEvidenceGaps={() => workflow.setIsEvidenceGapsExpanded(!workflow.isEvidenceGapsExpanded)}
          onReviewedEvidenceGapsChange={workflow.setReviewedEvidenceGaps}
          canUseWorkflowActions={canUseWorkflowActions}
          canApprove={canApprove}
          approveWarning={workflow.approveWarning}
          isGapAcknowledged={workflow.isGapAcknowledged}
          approveButtonLabel={approveButtonLabel}
          reviewMode={workflow.reviewMode}
          loading={workflow.loading}
          onApprove={() => {
            void workflow.handleApprove({
              selectedDraft: draftHistory.selectedDraft,
              isCompareMode: draftHistory.isCompareMode,
            });
          }}
          onToggleRevision={() => workflow.handleToggleRevisionMode(canUseWorkflowActions)}
          isRevisionHistoryExpanded={workflow.isRevisionHistoryExpanded}
          onToggleRevisionHistory={() => workflow.setIsRevisionHistoryExpanded(!workflow.isRevisionHistoryExpanded)}
          drafts={draftHistory.drafts}
          latestSnapshotTimestamp={draftHistory.latestSnapshotTimestamp}
          selectedDraft={draftHistory.selectedDraft}
          selectedDraftId={draftHistory.selectedDraftId}
          compareDraftId={draftHistory.compareDraftId}
          compareEnabled={draftHistory.compareEnabled}
          compareTargetDraft={draftHistory.compareTargetDraft}
          compareSegments={draftHistory.compareSegments}
          isViewingHistoricalDraft={draftHistory.isViewingHistoricalDraft}
          isCompareMode={draftHistory.isCompareMode}
          onSelectDraft={draftHistory.setSelectedDraftId}
          onSelectCompareDraft={draftHistory.setCompareSelection}
          feedback={workflow.feedback}
          excludedEvidenceCount={workflow.excludedEvidenceKeys.size}
          isSubmittingRevision={workflow.isSubmittingRevision}
          revisionProgress={workflow.revisionProgress}
          onFeedbackChange={workflow.setFeedback}
          onSubmitRevision={() => {
            void workflow.handleSubmitRevision({
              selectedDraft: draftHistory.selectedDraft,
              isCompareMode: draftHistory.isCompareMode,
              onSuccess: () => {
                draftHistory.pinToLatestDraft();
                setActiveEvidenceKey(null);
              },
            });
          }}
          finalVersionNumber={finalVersionNumber}
          approvalTimestamp={workflow.session?.approved_at ?? null}
          reviewerLabel={workflow.session?.reviewer_id ?? "Unassigned"}
          requiresGapAcknowledgement={workflow.session?.requires_gap_acknowledgement ?? workflow.requiresGapAcknowledgement}
          evidenceGapsAcknowledged={workflow.session?.evidence_gaps_acknowledged ?? false}
          evidenceGapsAcknowledgedAt={workflow.session?.evidence_gaps_acknowledged_at ?? null}
          error={workflow.error}
        />

        <EvidencePanel
          evidence={workflow.session?.evidence ?? []}
          citationByEvidenceKey={citationView.citationByEvidenceKey}
          citedEvidenceKeys={citationView.citedEvidenceKeys}
          displayedExcludedEvidenceKeys={displayedExcludedEvidenceKeys}
          activeEvidenceKey={activeEvidenceKey}
          isApproved={workflow.isApproved}
          isViewingHistoricalDraft={draftHistory.isViewingHistoricalDraft}
          canUseWorkflowActions={canUseWorkflowActions}
          loading={workflow.loading}
          onToggleEvidenceExclusion={workflow.toggleEvidenceExclusion}
        />
      </section>
    </main>
  );
}
