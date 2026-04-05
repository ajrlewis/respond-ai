import { formatQuestionType } from "@/lib/format";

type DraftHeaderProps = {
  isApproved: boolean;
  questionType: string | null;
  viewingLabel: string;
  selectedVersionLabel: string;
  selectedVersionTimestamp: string;
  workflowStatusLabel: string;
  selectedVersionStatus: string;
  compareLabel: string | null;
  revisionFeedback: string | null;
};

export function DraftHeader({
  isApproved,
  questionType,
  viewingLabel,
  selectedVersionLabel,
  selectedVersionTimestamp,
  workflowStatusLabel,
  selectedVersionStatus,
  compareLabel,
  revisionFeedback,
}: DraftHeaderProps) {
  return (
    <>
      <div className="answer-heading-row">
        <h3>{isApproved ? "Final Response (locked)" : "Draft Response"}</h3>
        <span className="question-type-chip">Question type: {formatQuestionType(questionType)}</span>
      </div>
      <p className="version-meta">Viewing: {viewingLabel}</p>
      <p className="version-meta">
        Version: {selectedVersionLabel} · {selectedVersionTimestamp}
      </p>
      <p className="version-meta">
        Status: {workflowStatusLabel} · View state: {selectedVersionStatus}
      </p>
      {compareLabel ? <p className="version-meta">Compare with: {compareLabel}</p> : null}
      {revisionFeedback ? <p className="draft-feedback-note">Revision feedback: {revisionFeedback}</p> : null}
    </>
  );
}
