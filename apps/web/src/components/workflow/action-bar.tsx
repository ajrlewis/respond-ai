type ActionBarProps = {
  canUseWorkflowActions: boolean;
  canApprove: boolean;
  approveWarning: boolean;
  isGapAcknowledged: boolean;
  confidenceScore: number | null;
  approveButtonLabel: string;
  reviewMode: "none" | "revise";
  loading: boolean;
  onApprove: () => void;
  onToggleRevision: () => void;
};

export function ActionBar({
  canUseWorkflowActions,
  canApprove,
  approveWarning,
  isGapAcknowledged,
  confidenceScore,
  approveButtonLabel,
  reviewMode,
  loading,
  onApprove,
  onToggleRevision,
}: ActionBarProps) {
  if (!canUseWorkflowActions) return null;

  return (
    <div className="review-actions action-bar">
      <button
        onClick={onApprove}
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
      <button onClick={onToggleRevision} disabled={loading} className="secondary">
        {reviewMode === "revise" ? "Cancel Revision" : "Revise"}
      </button>
    </div>
  );
}
