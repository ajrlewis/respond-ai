"use client";
import { useEffect, useMemo, useState } from "react";
import { ReviewV2UploadModal } from "@/components/review-v2/review-v2-upload-modal";
import { extractQuestions } from "@/components/review-v2/review-v2-shell-utils";
import {
  DocumentMetaPanel,
  GenerateCard,
  StageCard,
  WorkspaceHeader,
} from "@/components/review-v2/review-v2-workspace-sections";
import { ReviewV2EditingView } from "@/components/review-v2/review-v2-editing-view";
import {
  AI_STAGE_LABELS,
  GENERATION_STAGE_LABELS,
  INSUFFICIENT_EVIDENCE_WARNING,
  emptyStages,
  hasGlobalInsufficientEvidenceWarning,
  syncSectionContentAndEvidence,
  toQuestionContentMap,
  type Stage,
} from "@/components/review-v2/review-v2-shell-helpers";
import { reviewWorkspaceBranding } from "@/config/review-workspace";
import {
  aiReviseResponseDocument,
  approveResponseDocumentVersion,
  compareResponseDocumentVersions,
  createResponseDocument,
  createSampleResponseDocument,
  deleteResponseDocumentVersion,
  fetchResponseDocument,
  generateResponseDocument,
  saveResponseDocumentVersion,
  type ResponseVersionSummary,
  type ResponseDocument,
  type ResponseVersionComparison,
} from "@/lib/api";
import styles from "./review-v2-shell.module.css";
type ReviewV2ShellProps = {
  currentUsername?: string;
  isLoggingOut?: boolean;
  onLogout?: () => void;
};

type InspectionPanel = "compare" | null;
export function ReviewV2Shell({
  currentUsername,
  isLoggingOut = false,
  onLogout,
}: ReviewV2ShellProps) {
  const [document, setDocument] = useState<ResponseDocument | null>(null);
  const [editableSections, setEditableSections] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSavingVersion, setIsSavingVersion] = useState(false);
  const [isAskingAi, setIsAskingAi] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [deletingVersionId, setDeletingVersionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadHelperText, setUploadHelperText] = useState<string | null>(null);
  const [uploadErrorText, setUploadErrorText] = useState<string | null>(null);
  const [inspectionPanel, setInspectionPanel] = useState<InspectionPanel>(null);
  const [aiInstruction, setAiInstruction] = useState("");
  const [isAiComposerOpen, setIsAiComposerOpen] = useState(false);
  const [compareData, setCompareData] = useState<ResponseVersionComparison | null>(null);
  const [compareLeftVersionId, setCompareLeftVersionId] = useState<string | null>(null);
  const [compareRightVersionId, setCompareRightVersionId] = useState<string | null>(null);
  const [stages, setStages] = useState<Stage[]>(emptyStages(GENERATION_STAGE_LABELS));
  const selectedVersion = document?.selected_version ?? null;
  const versions = document?.versions ?? [];
  const questions = document?.questions ?? [];

  useEffect(() => {
    if (!document) return;
    setEditableSections(toQuestionContentMap(document));
    setCompareLeftVersionId((previous) => {
      if (previous && document.versions.some((version) => version.id === previous)) {
        return previous;
      }
      return document.versions.at(-2)?.id ?? document.versions.at(-1)?.id ?? null;
    });
    setCompareRightVersionId((previous) => {
      if (previous && document.versions.some((version) => version.id === previous)) {
        return previous;
      }
      return document.selected_version?.id ?? document.versions.at(-1)?.id ?? null;
    });
  }, [document]);

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(null), 3200);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  const hasGlobalEvidenceWarning = useMemo(() => {
    if (!document) return false;
    return hasGlobalInsufficientEvidenceWarning(document);
  }, [document]);

  const hasDraft = !!selectedVersion;
  const hasUnsavedChanges = useMemo(() => {
    if (!document || !selectedVersion) return false;
    for (const section of selectedVersion.sections) {
      const currentValue = (editableSections[section.question_id] ?? "").trim();
      const savedValue = section.content_markdown.trim();
      if (currentValue !== savedValue) {
        return true;
      }
    }
    return false;
  }, [document, editableSections, hasGlobalEvidenceWarning, selectedVersion]);
  const screenState = !document
    ? "start"
    : isGenerating
      ? "generating"
      : hasDraft
        ? "editing"
        : "ready_to_generate";
  async function runProgress(labels: string[], action: () => Promise<void>) {
    setStages(emptyStages(labels));
    let index = 0;
    const interval = window.setInterval(() => {
      setStages((previous) =>
        previous.map((stage, stageIndex) => {
          if (stageIndex < index) return { ...stage, status: "done" };
          if (stageIndex === index) return { ...stage, status: "running" };
          return { ...stage, status: "idle" };
        }),
      );
      index = Math.min(index + 1, labels.length - 1);
    }, 700);
    try {
      await action();
      setStages((previous) => previous.map((stage) => ({ ...stage, status: "done" })));
    } finally {
      window.clearInterval(interval);
    }
  }
  async function handleUseExamples() {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const nextDocument = await createSampleResponseDocument();
      setDocument(nextDocument);
      setUploadHelperText("Example questions loaded.");
      setUploadErrorText(null);
      setIsUploadModalOpen(false);
    } catch (caught) {
      setUploadErrorText(caught instanceof Error ? caught.message : "Failed to load example questions.");
      setError(caught instanceof Error ? caught.message : "Failed to load example questions.");
    } finally {
      setLoading(false);
    }
  }
  async function handleUploadFile(file: File) {
    setUploadErrorText(null);
    setUploadHelperText(null);
    setLoading(true);
    setError(null);
    setNotice(null);
    let parsedQuestions: string[] = [];
    try {
      const lower = file.name.toLowerCase();
      const canReadText = lower.endsWith(".md") || lower.endsWith(".markdown") || lower.endsWith(".txt");
      const sourceText = canReadText ? await file.text() : "";
      parsedQuestions = sourceText ? extractQuestions(sourceText) : [];
      const nextDocument = await createResponseDocument({
        title: file.name.replace(/\.[^.]+$/, ""),
        sourceFilename: file.name,
        sourceText: sourceText || undefined,
        questions: parsedQuestions,
        useExampleQuestions: !parsedQuestions.length,
        createdBy: currentUsername,
      });
      setDocument(nextDocument);
      setUploadHelperText(
        parsedQuestions.length
          ? `${parsedQuestions.length} question(s) loaded from ${file.name}.`
          : "No clear question list found. Example questions were loaded.",
      );
      setUploadErrorText(null);
      setIsUploadModalOpen(false);
    } catch (caught) {
      setUploadErrorText(caught instanceof Error ? caught.message : "Failed to process uploaded file.");
      setError(caught instanceof Error ? caught.message : "Failed to process uploaded file.");
    } finally {
      setLoading(false);
    }
  }
  async function handleGenerateDraft() {
    if (!document) return;
    setIsGenerating(true);
    setError(null);
    setNotice(null);
    try {
      await runProgress(GENERATION_STAGE_LABELS, async () => {
        const nextDocument = await generateResponseDocument(document.id, {
          tone: "formal",
          createdBy: currentUsername,
        });
        setDocument(nextDocument);
      });
      setNotice("Draft generated. Edit directly or request a revision.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to generate document draft.");
    } finally {
      setIsGenerating(false);
    }
  }
  async function handleSwitchVersion(versionId: string) {
    if (!document || loading) return;
    if (hasUnsavedChanges) {
      const proceed = window.confirm("You have unsaved edits. Switch versions and discard those edits?");
      if (!proceed) return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const nextDocument = await fetchResponseDocument(document.id, {
        selectedVersionId: versionId,
      });
      setDocument(nextDocument);
      setCompareData(null);
      setInspectionPanel((previous) => (previous === "compare" ? null : previous));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to switch versions.");
    } finally {
      setLoading(false);
    }
  }
  async function handleSaveVersion() {
    if (!document || !selectedVersion) return;
    setIsSavingVersion(true);
    setError(null);
    setNotice(null);
    try {
      const sections = questions.map((question) => {
        const existing = selectedVersion.sections.find((section) => section.question_id === question.id);
        const currentValue = (editableSections[question.id] ?? "").trim();
        const synced = syncSectionContentAndEvidence(currentValue, existing?.evidence_refs ?? []);
        return {
          question_id: question.id,
          content_markdown: synced.contentMarkdown,
          evidence_refs: synced.evidenceRefs,
          confidence_score: existing?.confidence_score ?? null,
          coverage_score: existing?.coverage_score ?? null,
        };
      });
      const nextDocument = await saveResponseDocumentVersion(document.id, {
        basedOnVersionId: selectedVersion.id,
        createdBy: currentUsername,
        sections,
      });
      setDocument(nextDocument);
      setNotice("Draft saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to save draft.");
    } finally {
      setIsSavingVersion(false);
    }
  }
  async function handleCompareVersions() {
    if (!document || !compareLeftVersionId || !compareRightVersionId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await compareResponseDocumentVersions(
        document.id,
        compareLeftVersionId,
        compareRightVersionId,
      );
      setCompareData(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to compare versions.");
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleComparePanel() {
    const nextPanel: InspectionPanel = inspectionPanel === "compare" ? null : "compare";
    setInspectionPanel(nextPanel);
    if (nextPanel !== "compare") return;
    await handleCompareVersions();
  }
  async function handleAskAI() {
    if (!document || !selectedVersion) return;
    const trimmed = aiInstruction.trim();
    if (!trimmed) {
      setError("Describe changes before submitting.");
      return;
    }
    setIsAskingAi(true);
    setError(null);
    setNotice(null);
    try {
      await runProgress(AI_STAGE_LABELS, async () => {
        const result = await aiReviseResponseDocument(document.id, {
          instruction: trimmed,
          baseVersionId: selectedVersion.id,
          tone: "formal",
        });
        const nextDocument = await saveResponseDocumentVersion(document.id, {
          basedOnVersionId: selectedVersion.id,
          createdBy: currentUsername,
          sections: result.revised_sections,
        });
        setDocument(nextDocument);
      });
      setNotice("Revision submitted and saved as a new version.");
      setAiInstruction("");
      setIsAiComposerOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to submit revision.");
    } finally {
      setIsAskingAi(false);
    }
  }

  async function handleApproveVersion() {
    if (!document || !selectedVersion) return;
    if (hasUnsavedChanges) {
      setError("Save draft changes before approving.");
      return;
    }
    setIsApproving(true);
    setError(null);
    setNotice(null);
    try {
      const nextDocument = await approveResponseDocumentVersion(document.id, selectedVersion.id);
      setDocument(nextDocument);
      setNotice(`Version ${selectedVersion.version_number} approved.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to approve this version.");
    } finally {
      setIsApproving(false);
    }
  }

  async function handleDeleteVersion(version: ResponseVersionSummary) {
    if (!document || deletingVersionId) return;
    const deletingActiveVersion = selectedVersion?.id === version.id;
    if (deletingActiveVersion && hasUnsavedChanges) {
      const discard = window.confirm("Delete this version and discard unsaved edits?");
      if (!discard) return;
    }
    const confirmed = window.confirm(`Delete Version ${version.version_number}? This cannot be undone.`);
    if (!confirmed) return;

    setDeletingVersionId(version.id);
    setError(null);
    setNotice(null);
    try {
      const nextDocument = await deleteResponseDocumentVersion(document.id, version.id);
      setDocument(nextDocument);
      setCompareData(null);
      setInspectionPanel((previous) => (previous === "compare" ? null : previous));
      setNotice(`Version ${version.version_number} deleted.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to delete version.");
    } finally {
      setDeletingVersionId(null);
    }
  }
  return (
    <main className={styles.page}>
      <WorkspaceHeader
        companyName={reviewWorkspaceBranding.companyName}
        logoSrc={reviewWorkspaceBranding.logoSrc}
        workspaceTitle={reviewWorkspaceBranding.workspaceTitle}
        workspaceSubtitle={reviewWorkspaceBranding.workspaceSubtitle}
        onLogout={onLogout}
        isLoggingOut={isLoggingOut}
      />
      <DocumentMetaPanel
        document={document}
        title={reviewWorkspaceBranding.startTitle}
        subtitle={reviewWorkspaceBranding.startSubtitle}
        loading={loading}
        onUpload={() => setIsUploadModalOpen(true)}
        onUseExamples={handleUseExamples}
      />
      {screenState !== "start" ? (
        <>
          {screenState === "ready_to_generate" ? (
            <GenerateCard generating={isGenerating} loading={loading} onGenerate={handleGenerateDraft} />
          ) : null}
          {screenState === "generating" ? (
            <StageCard
              title="Generating draft"
              subtitle="Preparing a document-level response across all sections."
              stages={stages}
            />
          ) : null}
          {screenState === "editing" && document && selectedVersion ? (
            <ReviewV2EditingView
              document={document}
              editableSections={editableSections}
              hasUnsavedChanges={hasUnsavedChanges}
              hasGlobalEvidenceWarning={hasGlobalEvidenceWarning}
              isAiComposerOpen={isAiComposerOpen}
              aiInstruction={aiInstruction}
              isAskingAi={isAskingAi}
              isSavingVersion={isSavingVersion}
              isApproving={isApproving}
              loading={loading}
              deletingVersionId={deletingVersionId}
              notice={notice}
              inspectionPanel={inspectionPanel}
              compareData={compareData}
              compareLeftVersionId={compareLeftVersionId}
              compareRightVersionId={compareRightVersionId}
              onSwitchVersion={handleSwitchVersion}
              onDeleteVersion={handleDeleteVersion}
              onToggleComposer={() => setIsAiComposerOpen((value) => !value)}
              onInstructionChange={setAiInstruction}
              onSubmitRevision={handleAskAI}
              onCancelRevision={() => setIsAiComposerOpen(false)}
              onSectionChange={(questionId, value) =>
                setEditableSections((previous) => ({ ...previous, [questionId]: value }))
              }
              onSaveVersion={handleSaveVersion}
              onApprove={handleApproveVersion}
              onToggleCompare={handleToggleComparePanel}
              onCompare={handleCompareVersions}
              onCompareLeftChange={setCompareLeftVersionId}
              onCompareRightChange={setCompareRightVersionId}
            />
          ) : null}
        </>
      ) : null}
      {error ? <p className={styles.errorBanner}>{error}</p> : null}
      <ReviewV2UploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onUseExamples={handleUseExamples}
        onUploadFile={handleUploadFile}
        helperText={uploadHelperText}
        errorText={uploadErrorText}
      />
    </main>
  );
}
