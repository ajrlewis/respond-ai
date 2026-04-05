type RevisionRequestPanelProps = {
  feedback: string;
  excludedEvidenceCount: number;
  loading: boolean;
  isSubmittingRevision: boolean;
  revisionProgress: string | null;
  onFeedbackChange: (feedback: string) => void;
  onSubmitRevision: () => void;
};

export function RevisionRequestPanel({
  feedback,
  excludedEvidenceCount,
  loading,
  isSubmittingRevision,
  revisionProgress,
  onFeedbackChange,
  onSubmitRevision,
}: RevisionRequestPanelProps) {
  return (
    <div className="revision-box">
      <h3>Revision request</h3>
      <label className="field-label" htmlFor="feedback">
        Feedback
      </label>
      <textarea
        id="feedback"
        rows={4}
        value={feedback}
        onChange={(event) => onFeedbackChange(event.target.value)}
        placeholder="Describe what should change in the draft."
      />
      {!!excludedEvidenceCount && (
        <p className="revision-exclusion-note">{excludedEvidenceCount} citation chunk(s) will be excluded from this redraft.</p>
      )}
      <div className="actions-row revision-submit-row">
        <button onClick={onSubmitRevision} disabled={loading}>
          Submit Revision
        </button>
        {isSubmittingRevision && loading && (
          <span className="inline-progress" aria-live="polite">
            {revisionProgress || "Updating revision..."}
          </span>
        )}
      </div>
    </div>
  );
}
