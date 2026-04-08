import { type ResponseDocument, type ResponseSection, type ResponseVersionComparison } from "@/lib/api";
import {
  AIComposer,
  ComparePanel,
  EditorSurface,
  VersionRow,
} from "@/components/workspace/workspace-sections";
import styles from "./shell.module.css";

type InspectionPanel = "compare" | null;
type RevisionScope = "selected_question" | "whole_document";

type ReviewV2EditingViewProps = {
  document: ResponseDocument;
  editableSections: Record<string, string>;
  hasUnsavedChanges: boolean;
  hasGlobalEvidenceWarning: boolean;
  isAiComposerOpen: boolean;
  aiInstruction: string;
  revisionScope: RevisionScope;
  revisionQuestionId: string | null;
  isAskingAi: boolean;
  isSavingVersion: boolean;
  isApproving: boolean;
  loading: boolean;
  isProcessing: boolean;
  deletingVersionId: string | null;
  notice: string | null;
  inspectionPanel: InspectionPanel;
  compareData: ResponseVersionComparison | null;
  compareLeftVersionId: string | null;
  compareRightVersionId: string | null;
  onSwitchVersion: (versionId: string) => void;
  onDeleteVersion: (version: ResponseDocument["versions"][number]) => void;
  onToggleComposer: () => void;
  onInstructionChange: (value: string) => void;
  onRevisionScopeChange: (scope: RevisionScope) => void;
  onRevisionQuestionChange: (questionId: string) => void;
  onSubmitRevision: () => void;
  onCancelRevision: () => void;
  onSectionChange: (questionId: string, value: string) => void;
  onSectionFocus: (questionId: string) => void;
  onSaveVersion: () => void;
  onApprove: () => void;
  onToggleCompare: () => void;
  onCompare: () => void;
  onCompareLeftChange: (value: string) => void;
  onCompareRightChange: (value: string) => void;
};

export function ReviewV2EditingView({
  document,
  editableSections,
  hasUnsavedChanges,
  hasGlobalEvidenceWarning,
  isAiComposerOpen,
  aiInstruction,
  revisionScope,
  revisionQuestionId,
  isAskingAi,
  isSavingVersion,
  isApproving,
  loading,
  isProcessing,
  deletingVersionId,
  notice,
  inspectionPanel,
  compareData,
  compareLeftVersionId,
  compareRightVersionId,
  onSwitchVersion,
  onDeleteVersion,
  onToggleComposer,
  onInstructionChange,
  onRevisionScopeChange,
  onRevisionQuestionChange,
  onSubmitRevision,
  onCancelRevision,
  onSectionChange,
  onSectionFocus,
  onSaveVersion,
  onApprove,
  onToggleCompare,
  onCompare,
  onCompareLeftChange,
  onCompareRightChange,
}: ReviewV2EditingViewProps) {
  const selectedVersion = document.selected_version;
  if (!selectedVersion) return null;
  const sectionsByQuestionId = Object.fromEntries(
    selectedVersion.sections.map((section) => [section.question_id, section] as const),
  ) as Record<string, ResponseSection | undefined>;

  return (
    <>
      <VersionRow
        versions={document.versions}
        selectedVersionId={selectedVersion.id}
        loading={loading || !!deletingVersionId || isProcessing}
        onSelect={onSwitchVersion}
        onDelete={onDeleteVersion}
      />
      <section className={styles.revisionToggleRow}>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={onToggleComposer}
          disabled={isAskingAi || loading}
        >
          {isAiComposerOpen ? "Hide suggestions" : "Suggest changes"}
        </button>
        {selectedVersion.is_final ? <p className={styles.finalTag}>Approved version</p> : null}
        {isAiComposerOpen ? (
          <div className={styles.revisionComposerOverlay}>
            <AIComposer
              instruction={aiInstruction}
              askingAi={isAskingAi}
              loading={loading}
              mode="overlay"
              scope={revisionScope}
              questions={document.questions.map((question) => ({
                id: question.id,
                label: question.extracted_text,
              }))}
              selectedQuestionId={revisionQuestionId}
              onInstructionChange={onInstructionChange}
              onScopeChange={onRevisionScopeChange}
              onQuestionChange={onRevisionQuestionChange}
              onApply={onSubmitRevision}
              onCancel={onCancelRevision}
            />
          </div>
        ) : null}
      </section>
      <EditorSurface
        questions={document.questions}
        sectionsByQuestionId={sectionsByQuestionId}
        editableSections={editableSections}
        hasUnsavedChanges={hasUnsavedChanges}
        globalNotice={
          hasGlobalEvidenceWarning
            ? "Some responses need additional internal supporting material before final approval."
            : null
        }
        onSectionChange={onSectionChange}
        onSectionFocus={onSectionFocus}
      />
      <section className={styles.reviewActions}>
        <div className={styles.reviewActionsPrimary}>
          <button
            type="button"
            onClick={onApprove}
            disabled={loading || isSavingVersion || isAskingAi || isApproving || hasUnsavedChanges}
          >
            {isApproving ? "Approving..." : selectedVersion.is_final ? "Approved" : "Approve"}
          </button>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={onSaveVersion}
            disabled={!hasUnsavedChanges || isSavingVersion || isProcessing || loading || isApproving}
          >
            {isSavingVersion ? "Saving..." : "Save draft"}
          </button>
          {notice ? <p className={styles.inlineNotice}>{notice}</p> : null}
        </div>
      </section>
      {hasUnsavedChanges ? (
        <p className={styles.actionHint}>Save draft changes before approving.</p>
      ) : null}
      <section className={styles.secondaryActions}>
        <button
          type="button"
          className={inspectionPanel === "compare" ? styles.secondaryButton : styles.ghostButton}
          onClick={onToggleCompare}
          disabled={loading}
        >
          Compare versions
        </button>
      </section>
      {inspectionPanel === "compare" && compareData ? (
        <ComparePanel
          compareData={compareData}
          versions={document.versions}
          leftVersionId={compareLeftVersionId}
          rightVersionId={compareRightVersionId}
          onLeftChange={onCompareLeftChange}
          onRightChange={onCompareRightChange}
          onRefresh={onCompare}
        />
      ) : null}
      {inspectionPanel === "compare" && !compareData ? (
        <section className={styles.sidePanel}>
          <h3>Version comparison</h3>
          <p className={styles.questionMeta}>Loading comparison...</p>
        </section>
      ) : null}
    </>
  );
}
