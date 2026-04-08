import { type ReactNode, useMemo } from "react";

import { type SessionStatus } from "@/lib/api";
import { statusLabel, tokenizeNumberedCitations } from "@/lib/workflow";

import { type UseWorkflowResult } from "@/hooks/use-workflow";

import styles from "./document.module.css";

type ReviewV2DocumentProps = {
  workflow: UseWorkflowResult;
  sessionStatus: SessionStatus | null;
  selectedVersionLabel: string;
  selectedVersionStatus: string;
  selectedDraftTimestamp: string;
  answerText: string;
  editableAnswerText: string;
  canEdit: boolean;
  hasInlineEdits: boolean;
  isRevisionComposerOpen: boolean;
  inlineEditWarning: string | null;
  activeEvidenceKey: string | null;
  activeCitationNumber: number | null;
  citationKeyByNumber: Map<number, string>;
  excludedEvidenceCount: number;
  revisionFeedback: string;
  revisionProgress: string | null;
  isSubmittingRevision: boolean;
  error: string | null;
  onEditableAnswerTextChange: (value: string) => void;
  onRevisionFeedbackChange: (value: string) => void;
  onCancelRevision: () => void;
  onSubmitRevision: () => void;
  onCitationClick: (citationNumber: number, evidenceKey: string) => void;
};

function renderAnswerWithCitations(
  answerText: string,
  citationKeyByNumber: Map<number, string>,
  activeCitationNumber: number | null,
  activeEvidenceKey: string | null,
  onCitationClick: (citationNumber: number, evidenceKey: string) => void,
): ReactNode[] {
  return tokenizeNumberedCitations(answerText).map((token, index) => {
    if (token.kind === "text") {
      return <span key={`text-${index}`}>{token.value}</span>;
    }

    const evidenceTarget = citationKeyByNumber.get(token.value);
    if (!evidenceTarget) {
      return <span key={`citation-${index}`}>{token.label}</span>;
    }

    const isActive =
      token.value === activeCitationNumber || evidenceTarget === activeEvidenceKey;

    return (
      <button
        key={`citation-${index}-${token.value}`}
        type="button"
        className={`${styles.inlineCitation}${isActive ? ` ${styles.inlineCitationActive}` : ""}`}
        onClick={() => onCitationClick(token.value, evidenceTarget)}
      >
        {token.label}
      </button>
    );
  });
}

export function ReviewV2Document({
  workflow,
  sessionStatus,
  selectedVersionLabel,
  selectedVersionStatus,
  selectedDraftTimestamp,
  answerText,
  editableAnswerText,
  canEdit,
  hasInlineEdits,
  isRevisionComposerOpen,
  inlineEditWarning,
  activeEvidenceKey,
  activeCitationNumber,
  citationKeyByNumber,
  excludedEvidenceCount,
  revisionFeedback,
  revisionProgress,
  isSubmittingRevision,
  error,
  onEditableAnswerTextChange,
  onRevisionFeedbackChange,
  onCancelRevision,
  onSubmitRevision,
  onCitationClick,
}: ReviewV2DocumentProps) {
  const inlineCitations = useMemo(() => {
    const numbers = tokenizeNumberedCitations(editableAnswerText)
      .filter((token): token is { kind: "citation"; value: number; label: string } => token.kind === "citation")
      .map((token) => token.value);

    return Array.from(new Set(numbers));
  }, [editableAnswerText]);

  const documentMeta = [selectedVersionStatus];
  if (selectedDraftTimestamp) {
    documentMeta.push(`Updated ${selectedDraftTimestamp}`);
  }

  return (
    <article className={styles.documentCanvas}>
      <div className={styles.documentHeader}>
        <div>
          <p className={styles.documentLabel}>Draft</p>
          <h2>{selectedVersionLabel}</h2>
          {documentMeta.length ? (
            <p className={styles.documentMeta}>{documentMeta.join(" · ")}</p>
          ) : null}
        </div>
        <span className={styles.statusChip}>{statusLabel(sessionStatus ?? "draft")}</span>
      </div>

      {error ? <p className={styles.errorBanner}>{error}</p> : null}
      {inlineEditWarning ? <p className={styles.errorBanner}>{inlineEditWarning}</p> : null}

      {!workflow.session ? (
        <div className={styles.emptyState}>
          <p>Generate a draft to start review.</p>
        </div>
      ) : (
        <>
          <div className={styles.documentBody}>
            {canEdit ? (
              <textarea
                className={styles.documentEditor}
                value={editableAnswerText}
                onChange={(event) => onEditableAnswerTextChange(event.target.value)}
                rows={16}
                placeholder="Draft response will appear here."
              />
            ) : (
              <div className={styles.readOnlyText}>
                {answerText
                  ? renderAnswerWithCitations(
                      answerText,
                      citationKeyByNumber,
                      activeCitationNumber,
                      activeEvidenceKey,
                      onCitationClick,
                    )
                  : "No draft content yet."}
              </div>
            )}
          </div>

          {canEdit && inlineCitations.length ? (
            <div className={styles.citationRow}>
              <p className={styles.citationLabel}>Citations used</p>
              {inlineCitations.map((citationNumber) => {
                const evidenceKey = citationKeyByNumber.get(citationNumber);
                const isActive =
                  citationNumber === activeCitationNumber ||
                  (!!evidenceKey && evidenceKey === activeEvidenceKey);

                return (
                  <button
                    key={`inline-citation-${citationNumber}`}
                    type="button"
                    className={isActive ? styles.citationButtonActive : styles.citationButton}
                    disabled={!evidenceKey}
                    onClick={() => {
                      if (!evidenceKey) return;
                      onCitationClick(citationNumber, evidenceKey);
                    }}
                  >
                    [{citationNumber}]
                  </button>
                );
              })}
            </div>
          ) : null}

          {canEdit ? (
            <p className={styles.editorHint}>
              {hasInlineEdits
                ? "You have unsaved inline edits."
                : "Edit directly in the draft, then approve or request revision."}
            </p>
          ) : null}

          {isRevisionComposerOpen && canEdit ? (
            <section className={styles.revisionComposer}>
              <label className={styles.revisionLabel} htmlFor="revision-feedback-v2">
                Describe changes
              </label>
              <textarea
                id="revision-feedback-v2"
                value={revisionFeedback}
                onChange={(event) => onRevisionFeedbackChange(event.target.value)}
                rows={3}
                placeholder="Describe what should change..."
              />
              <div className={styles.revisionActions}>
                <button
                  type="button"
                  onClick={onSubmitRevision}
                  disabled={workflow.loading || isSubmittingRevision}
                >
                  {isSubmittingRevision ? "Submitting..." : "Submit"}
                </button>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={onCancelRevision}
                >
                  Cancel
                </button>
              </div>
              <p className={styles.revisionMeta}>
                {excludedEvidenceCount} excluded evidence chunk(s)
                {revisionProgress ? ` · ${revisionProgress}` : ""}
              </p>
            </section>
          ) : null}
        </>
      )}
    </article>
  );
}
