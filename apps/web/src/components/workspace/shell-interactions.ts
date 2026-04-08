import { useCallback } from "react";

import { type UseDraftHistoryResult } from "@/hooks/use-draft-history";
import { type UseWorkflowResult } from "@/hooks/use-workflow";
import { type ReviewRailTab } from "@/lib/review-models";

type UseReviewV2InteractionsArgs = {
  workflow: UseWorkflowResult;
  draftHistory: UseDraftHistoryResult;
  canUseWorkflowActions: boolean;
  hasInlineEdits: boolean;
  editableAnswerText: string;
  sourceAnswerText: string;
  setEditableAnswerText: (value: string) => void;
  setInlineEditWarning: (value: string | null) => void;
  setIsRevisionComposerOpen: (value: boolean) => void;
  setActiveEvidenceKey: (value: string | null) => void;
  setActiveCitationNumber: (value: number | null) => void;
  setIsAssistPanelOpen: (value: boolean) => void;
  setRightTab: (tab: ReviewRailTab) => void;
};

export function useReviewV2Interactions({
  workflow,
  draftHistory,
  canUseWorkflowActions,
  hasInlineEdits,
  editableAnswerText,
  sourceAnswerText,
  setEditableAnswerText,
  setInlineEditWarning,
  setIsRevisionComposerOpen,
  setActiveEvidenceKey,
  setActiveCitationNumber,
  setIsAssistPanelOpen,
  setRightTab,
}: UseReviewV2InteractionsArgs) {
  const handleGenerateDraft = useCallback(() => {
    void workflow.handleGenerateDraft({
      onBeforeStart: () => {
        draftHistory.resetHistory();
        setIsRevisionComposerOpen(false);
        setInlineEditWarning(null);
        setActiveEvidenceKey(null);
        setActiveCitationNumber(null);
        setIsAssistPanelOpen(false);
      },
    });
  }, [
    draftHistory,
    setActiveCitationNumber,
    setActiveEvidenceKey,
    setInlineEditWarning,
    setIsAssistPanelOpen,
    setIsRevisionComposerOpen,
    workflow,
  ]);

  const handleApproveAction = useCallback(() => {
    if (hasInlineEdits) {
      const approveSavedVersion = window.confirm(
        "You have unsaved inline edits. Approve the latest saved version without these edits?",
      );
      if (!approveSavedVersion) {
        setInlineEditWarning("Submit a revision to apply inline edits before approval.");
        setIsRevisionComposerOpen(true);
        return;
      }
      setEditableAnswerText(sourceAnswerText);
    }

    setInlineEditWarning(null);
    void workflow.handleApprove({
      selectedDraft: draftHistory.selectedDraft,
      isCompareMode: false,
    });
  }, [
    draftHistory.selectedDraft,
    hasInlineEdits,
    setEditableAnswerText,
    setInlineEditWarning,
    setIsRevisionComposerOpen,
    sourceAnswerText,
    workflow,
  ]);

  const handleSubmitRevision = useCallback(() => {
    if (!canUseWorkflowActions) return;

    const trimmedFeedback = workflow.feedback.trim();
    const inlineFeedback = hasInlineEdits
      ? `Apply the reviewed edits below while preserving citation numbering:\n\n${editableAnswerText}`
      : "";

    const feedbackOverride = inlineFeedback
      ? trimmedFeedback
        ? `${trimmedFeedback}\n\n${inlineFeedback}`
        : inlineFeedback
      : undefined;

    setInlineEditWarning(null);
    void workflow.handleSubmitRevision({
      selectedDraft: draftHistory.selectedDraft,
      isCompareMode: false,
      feedbackOverride,
      onSuccess: () => {
        draftHistory.pinToLatestDraft();
        setIsRevisionComposerOpen(false);
        setActiveEvidenceKey(null);
        setActiveCitationNumber(null);
      },
    });
  }, [
    canUseWorkflowActions,
    draftHistory,
    editableAnswerText,
    hasInlineEdits,
    setActiveCitationNumber,
    setActiveEvidenceKey,
    setInlineEditWarning,
    setIsRevisionComposerOpen,
    workflow,
  ]);

  const handleExportAnswer = useCallback(() => {
    if (!sourceAnswerText.trim()) return;

    const blob = new Blob([sourceAnswerText], {
      type: "text/plain;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "response-draft.txt";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }, [sourceAnswerText]);

  const openAssistPanel = useCallback(
    (tab: ReviewRailTab) => {
      setRightTab(tab);
      setIsAssistPanelOpen(true);
    },
    [setIsAssistPanelOpen, setRightTab],
  );

  const handleCitationClick = useCallback(
    (citationNumber: number, evidenceKey: string) => {
      setActiveCitationNumber(citationNumber);
      setActiveEvidenceKey(evidenceKey);
      setRightTab("evidence");
      setIsAssistPanelOpen(true);
    },
    [setActiveCitationNumber, setActiveEvidenceKey, setIsAssistPanelOpen, setRightTab],
  );

  const handleJumpToCitation = useCallback(
    (evidenceKey: string, citationNumber: number | null) => {
      if (!citationNumber) return;
      setActiveCitationNumber(citationNumber);
      setActiveEvidenceKey(evidenceKey);
      setRightTab("evidence");
      setIsAssistPanelOpen(true);
    },
    [setActiveCitationNumber, setActiveEvidenceKey, setIsAssistPanelOpen, setRightTab],
  );

  return {
    handleGenerateDraft,
    handleApproveAction,
    handleSubmitRevision,
    handleExportAnswer,
    openAssistPanel,
    handleCitationClick,
    handleJumpToCitation,
  };
}
