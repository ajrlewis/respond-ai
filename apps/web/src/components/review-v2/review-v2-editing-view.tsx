import { type ResponseDocument, type ResponseSection, type ResponseVersionComparison } from "@/lib/api";
import {
  AllSourcesPanel,
  AIComposer,
  ComparePanel,
  EditorSurface,
  VersionRow,
} from "@/components/review-v2/review-v2-workspace-sections";
import styles from "./review-v2-shell.module.css";

type InspectionPanel = "sources" | "compare" | null;

type ReviewV2EditingViewProps = {
  document: ResponseDocument;
  editableSections: Record<string, string>;
  hasUnsavedChanges: boolean;
  hasGlobalEvidenceWarning: boolean;
  isAiComposerOpen: boolean;
  aiInstruction: string;
  isAskingAi: boolean;
  isSavingVersion: boolean;
  isApproving: boolean;
  loading: boolean;
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
  onSubmitRevision: () => void;
  onCancelRevision: () => void;
  onSectionChange: (questionId: string, value: string) => void;
  onSaveVersion: () => void;
  onApprove: () => void;
  onToggleSources: () => void;
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
  isAskingAi,
  isSavingVersion,
  isApproving,
  loading,
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
  onSubmitRevision,
  onCancelRevision,
  onSectionChange,
  onSaveVersion,
  onApprove,
  onToggleSources,
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
        loading={loading || !!deletingVersionId}
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
          {isAiComposerOpen ? "Hide revision request" : "Request revision"}
        </button>
        {selectedVersion.is_final ? <p className={styles.finalTag}>Approved version</p> : null}
      </section>
      {isAiComposerOpen ? (
        <AIComposer
          instruction={aiInstruction}
          askingAi={isAskingAi}
          loading={loading}
          onInstructionChange={onInstructionChange}
          onApply={onSubmitRevision}
          onCancel={onCancelRevision}
        />
      ) : null}
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
            disabled={!hasUnsavedChanges || isSavingVersion || loading || isApproving}
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
          className={inspectionPanel === "sources" ? styles.secondaryButton : styles.ghostButton}
          onClick={onToggleSources}
        >
          Show all sources
        </button>
        <button
          type="button"
          className={inspectionPanel === "compare" ? styles.secondaryButton : styles.ghostButton}
          onClick={onToggleCompare}
          disabled={loading}
        >
          Compare versions
        </button>
      </section>
      {inspectionPanel === "sources" ? (
        <AllSourcesPanel questions={document.questions} sections={selectedVersion.sections} />
      ) : null}
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
