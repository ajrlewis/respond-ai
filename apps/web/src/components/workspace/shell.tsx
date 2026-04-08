"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { ReviewV2UploadModal } from "@/components/workspace/upload-modal";
import { extractQuestions } from "@/components/workspace/shell-utils";
import {
  DocumentMetaPanel,
  GeneratingDraftPreview,
  GenerateCard,
  ProcessingStatusStrip,
  StageCard,
  VersionRow,
  WorkspaceHeader,
} from "@/components/workspace/workspace-sections";
import { ReviewV2EditingView } from "@/components/workspace/editing-view";
import {
  AI_STAGE_LABELS,
  GENERATION_STAGE_LABELS,
  emptyStages,
  filterChangedRevisedSections,
  hasGlobalInsufficientEvidenceWarning,
  markAllStagesDone,
  syncSectionContentAndEvidence,
  toQuestionContentMap,
  updateStagesFromServer,
  type Stage,
} from "@/components/workspace/shell-helpers";
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
  openResponseDocumentEventsStream,
  saveResponseDocumentVersion,
  type EvidenceItem,
  type ResponseVersionSummary,
  type ResponseDocument,
  type ResponseVersionComparison,
  type ResponseDocumentWorkflowEvent,
} from "@/lib/api";
import styles from "./shell.module.css";
type ReviewV2ShellProps = {
  currentUsername?: string;
  isLoggingOut?: boolean;
  onLogout?: () => void;
};

type InspectionPanel = "compare" | null;
type RunKind = "generation" | "revision";
type RunOperation = "generation" | "revision";
type RevisionScope = "selected_question" | "whole_document";

function runCopy(kind: RunKind): { title: string; subtitle: string } {
  if (kind === "revision") {
    return {
      title: "Applying revision",
      subtitle: "Updating draft content based on your requested changes.",
    };
  }

  return {
    title: "Generating draft",
    subtitle: "Preparing a document-level response across all sections.",
  };
}

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
  const [activeRunKind, setActiveRunKind] = useState<RunKind | null>(null);
  const [lastRunKind, setLastRunKind] = useState<RunKind | null>(null);
  const [hasRunHistory, setHasRunHistory] = useState(false);
  const [aiInstruction, setAiInstruction] = useState("");
  const [isAiComposerOpen, setIsAiComposerOpen] = useState(false);
  const [revisionScope, setRevisionScope] = useState<RevisionScope>("selected_question");
  const [revisionQuestionId, setRevisionQuestionId] = useState<string | null>(null);
  const [focusedQuestionId, setFocusedQuestionId] = useState<string | null>(null);
  const [compareData, setCompareData] = useState<ResponseVersionComparison | null>(null);
  const [compareLeftVersionId, setCompareLeftVersionId] = useState<string | null>(null);
  const [compareRightVersionId, setCompareRightVersionId] = useState<string | null>(null);
  const [stages, setStages] = useState<Stage[]>(emptyStages(GENERATION_STAGE_LABELS));
  const [runScopeLabel, setRunScopeLabel] = useState<string | null>(null);
  const [generatingEvidenceByQuestionId, setGeneratingEvidenceByQuestionId] = useState<Record<string, EvidenceItem[]>>({});
  const runEventsRef = useRef<EventSource | null>(null);
  const selectedVersion = document?.selected_version ?? null;
  const versions = document?.versions ?? [];
  const questions = document?.questions ?? [];
  const isProcessing = isGenerating || isAskingAi;
  const runKindForDisplay = activeRunKind ?? lastRunKind;
  const runContent = runKindForDisplay ? runCopy(runKindForDisplay) : runCopy("generation");

  useEffect(() => {
    if (!document) return;
    setEditableSections(toQuestionContentMap(document));
    const questionIds = document.questions.map((question) => question.id);
    const fallbackQuestionId = focusedQuestionId && questionIds.includes(focusedQuestionId)
      ? focusedQuestionId
      : (questionIds[0] ?? null);
    setRevisionQuestionId((previous) => {
      if (previous && questionIds.includes(previous)) {
        return previous;
      }
      return fallbackQuestionId;
    });
    if (focusedQuestionId && !questionIds.includes(focusedQuestionId)) {
      setFocusedQuestionId(questionIds[0] ?? null);
    }
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
  }, [document, focusedQuestionId]);

  useEffect(() => {
    return () => {
      runEventsRef.current?.close();
      runEventsRef.current = null;
    };
  }, []);

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
    : hasDraft
      ? "editing"
      : isGenerating
        ? "generating"
        : "ready_to_generate";

  async function runProgress(params: {
    documentId: string;
    operation: RunOperation;
    labels: string[];
    action: (runId: string) => Promise<void>;
  }): Promise<void> {
    const { documentId, operation, labels, action } = params;
    const runId = crypto.randomUUID();
    setStages(emptyStages(labels));
    setRunScopeLabel(null);
    if (operation === "generation") {
      setGeneratingEvidenceByQuestionId({});
    }
    runEventsRef.current?.close();
    const source = openResponseDocumentEventsStream(documentId);
    runEventsRef.current = source;

    const handleWorkflowState = (event: Event) => {
      const message = event as MessageEvent<string>;
      let payload: ResponseDocumentWorkflowEvent;
      try {
        payload = JSON.parse(message.data) as ResponseDocumentWorkflowEvent;
      } catch {
        return;
      }

      const metadata = payload.metadata ?? {};
      const eventRunId = typeof metadata.run_id === "string" ? metadata.run_id : null;
      const eventOperation = typeof metadata.operation === "string" ? metadata.operation : null;
      if (eventRunId !== runId || eventOperation !== operation) return;

      if (payload.error) {
        setError(payload.error);
      }

      const stageLabel = typeof metadata.stage_label === "string" ? metadata.stage_label : null;
      const stageStatus = metadata.stage_status;
      if (stageLabel && (stageStatus === "running" || stageStatus === "done")) {
        setStages((previous) => updateStagesFromServer(previous, stageLabel, stageStatus));
      }
      const questionIndex =
        typeof metadata.question_index === "number" ? metadata.question_index : null;
      const questionTotal =
        typeof metadata.question_total === "number" ? metadata.question_total : null;
      if (
        questionIndex &&
        questionTotal &&
        Number.isFinite(questionIndex) &&
        Number.isFinite(questionTotal)
      ) {
        setRunScopeLabel(`Question ${questionIndex} of ${questionTotal}`);
      }

      if (payload.reason === "run_completed") {
        setStages((previous) => markAllStagesDone(previous));
        setActiveRunKind(null);
        if (operation === "generation") {
          setIsGenerating(false);
          setLastRunKind("generation");
          void fetchResponseDocument(documentId)
            .then((nextDocument) => {
              setDocument(nextDocument);
            })
            .catch(() => {
              // keep current state if refresh fails; primary action response can still hydrate
            });
        } else {
          setIsAskingAi(false);
          setLastRunKind("revision");
        }
      }

      const completedQuestionId =
        typeof metadata.question_id === "string" ? metadata.question_id : null;
      const completedContent =
        typeof metadata.content_markdown === "string" ? metadata.content_markdown : null;
      const questionCompleted = metadata.question_completed === true;
      if (operation === "generation" && questionCompleted && completedQuestionId && completedContent !== null) {
        setEditableSections((previous) => ({
          ...previous,
          [completedQuestionId]: completedContent,
        }));
        const evidenceRefs = Array.isArray(metadata.evidence_refs)
          ? (metadata.evidence_refs as EvidenceItem[])
          : [];
        setGeneratingEvidenceByQuestionId((previous) => ({
          ...previous,
          [completedQuestionId]: evidenceRefs,
        }));
      }
    };

    source.addEventListener("workflow_state", handleWorkflowState);

    try {
      await action(runId);
      setStages((previous) => markAllStagesDone(previous));
    } finally {
      source.removeEventListener("workflow_state", handleWorkflowState);
      source.close();
      if (runEventsRef.current === source) runEventsRef.current = null;
    }
  }
  async function handleUseExamples() {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const nextDocument = await createSampleResponseDocument();
      setDocument(nextDocument);
      setStages(emptyStages(GENERATION_STAGE_LABELS));
      setActiveRunKind(null);
      setLastRunKind(null);
      setHasRunHistory(false);
      setInspectionPanel(null);
      setGeneratingEvidenceByQuestionId({});
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
      setStages(emptyStages(GENERATION_STAGE_LABELS));
      setActiveRunKind(null);
      setLastRunKind(null);
      setHasRunHistory(false);
      setInspectionPanel(null);
      setGeneratingEvidenceByQuestionId({});
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
    setActiveRunKind("generation");
    setHasRunHistory(true);
    setInspectionPanel(null);
    setIsGenerating(true);
    setError(null);
    setNotice(null);
    try {
      await runProgress({
        documentId: document.id,
        operation: "generation",
        labels: GENERATION_STAGE_LABELS,
        action: async (runId) => {
          const nextDocument = await generateResponseDocument(document.id, {
            tone: "formal",
            createdBy: currentUsername,
            runId,
          });
          setDocument(nextDocument);
        },
      });
      setLastRunKind("generation");
      setNotice("Draft generated. Edit directly or request a revision.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to generate document draft.");
    } finally {
      setIsGenerating(false);
      setActiveRunKind(null);
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

  function handleRevisionScopeChange(scope: RevisionScope) {
    setRevisionScope(scope);
    if (scope === "selected_question" && !revisionQuestionId) {
      setRevisionQuestionId(focusedQuestionId ?? questions[0]?.id ?? null);
    }
  }

  async function handleAskAI() {
    if (!document || !selectedVersion) return;
    const trimmed = aiInstruction.trim();
    if (!trimmed) {
      setError("Describe changes before submitting.");
      return;
    }
    const scopedQuestionId =
      revisionScope === "selected_question"
        ? (revisionQuestionId ?? focusedQuestionId ?? questions[0]?.id ?? null)
        : null;
    if (revisionScope === "selected_question" && !scopedQuestionId) {
      setError("Select a question to revise.");
      return;
    }
    setActiveRunKind("revision");
    setHasRunHistory(true);
    setInspectionPanel(null);
    setIsAskingAi(true);
    setError(null);
    setNotice(null);
    let didSaveRevision = false;
    try {
      await runProgress({
        documentId: document.id,
        operation: "revision",
        labels: AI_STAGE_LABELS,
        action: async (runId) => {
          const result = await aiReviseResponseDocument(document.id, {
            instruction: trimmed,
            baseVersionId: selectedVersion.id,
            questionId: scopedQuestionId,
            tone: "formal",
            runId,
          });
          const baseSectionsByQuestionId = Object.fromEntries(
            selectedVersion.sections.map((section) => [section.question_id, section.content_markdown] as const),
          );
          const changedSections = filterChangedRevisedSections(
            baseSectionsByQuestionId,
            result.revised_sections,
          );
          if (!changedSections.length) {
            setNotice(
              revisionScope === "selected_question"
                ? "No updates were applied to the selected question. Try a more specific request."
                : "No updates were applied to the draft. Try a more specific request.",
            );
            return;
          }
          const nextDocument = await saveResponseDocumentVersion(document.id, {
            basedOnVersionId: selectedVersion.id,
            createdBy: currentUsername,
            sections: changedSections,
          });
          setDocument(nextDocument);
          didSaveRevision = true;
        },
      });
      setLastRunKind("revision");
      if (didSaveRevision) {
        setNotice(
          revisionScope === "selected_question"
            ? "Revision submitted for the selected question and saved as a new version."
            : "Revision submitted for the full document and saved as a new version.",
        );
        setAiInstruction("");
        setIsAiComposerOpen(false);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to submit revision.");
    } finally {
      setIsAskingAi(false);
      setActiveRunKind(null);
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
          {screenState === "generating" && document ? (
            <>
              <StageCard title={runContent.title} stages={stages} scopeLabel={runScopeLabel} />
              {selectedVersion ? (
                <VersionRow
                  versions={versions}
                  selectedVersionId={selectedVersion.id}
                  loading={loading || isGenerating || !!deletingVersionId}
                  onSelect={handleSwitchVersion}
                  onDelete={handleDeleteVersion}
                />
              ) : null}
              <GeneratingDraftPreview
                questions={document.questions}
                sectionsByQuestionId={editableSections}
                evidenceByQuestionId={generatingEvidenceByQuestionId}
              />
            </>
          ) : null}
          {screenState === "editing" && document && selectedVersion ? (
            <>
              {hasRunHistory && isProcessing ? (
                <ProcessingStatusStrip
                  title={runContent.title}
                  stages={stages}
                  isRunning={isProcessing}
                  scopeLabel={runScopeLabel}
                />
              ) : null}
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
                isProcessing={isProcessing}
                deletingVersionId={deletingVersionId}
                notice={notice}
                inspectionPanel={inspectionPanel}
                compareData={compareData}
                compareLeftVersionId={compareLeftVersionId}
                compareRightVersionId={compareRightVersionId}
                onSwitchVersion={handleSwitchVersion}
                onDeleteVersion={handleDeleteVersion}
                revisionScope={revisionScope}
                revisionQuestionId={revisionQuestionId}
                onToggleComposer={() => {
                  setIsAiComposerOpen((value) => !value);
                  if (!revisionQuestionId) {
                    setRevisionQuestionId(focusedQuestionId ?? questions[0]?.id ?? null);
                  }
                }}
                onInstructionChange={setAiInstruction}
                onRevisionScopeChange={handleRevisionScopeChange}
                onRevisionQuestionChange={setRevisionQuestionId}
                onSubmitRevision={handleAskAI}
                onCancelRevision={() => setIsAiComposerOpen(false)}
                onSectionChange={(questionId, value) =>
                  setEditableSections((previous) => ({ ...previous, [questionId]: value }))
                }
                onSectionFocus={setFocusedQuestionId}
                onSaveVersion={handleSaveVersion}
                onApprove={handleApproveVersion}
                onToggleCompare={handleToggleComparePanel}
                onCompare={handleCompareVersions}
                onCompareLeftChange={setCompareLeftVersionId}
                onCompareRightChange={setCompareRightVersionId}
              />
            </>
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
