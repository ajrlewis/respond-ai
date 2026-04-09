import {
  type DraftDiffSegment,
  type EvidenceItem,
  type ResponseDocument,
  type ResponseSection,
  type ResponseVersionSummary,
  type ResponseVersionComparison,
} from "@/lib/api";
import { useState } from "react";

import styles from "./shell.module.css";

type Stage = {
  label: string;
  status: "idle" | "running" | "done";
};

type AgentStatusNodeProps = {
  statusText: string;
  subText?: string | null;
  isRunning?: boolean;
};

function stageStatusLabel(status: Stage["status"]): string {
  if (status === "running") return "Running";
  if (status === "done") return "Done";
  return "Pending";
}

function activeStageLabel(stages: Stage[]): string {
  const hasProgress = stages.some((stage) => stage.status !== "idle");
  if (!hasProgress) return "";
  const running = stages.find((stage) => stage.status === "running");
  if (running) return running.label;
  const pending = stages.find((stage) => stage.status === "idle");
  if (pending) return pending.label;
  return "Processing complete";
}

function stageTickerLabel(stageLabel: string, scopeLabel?: string | null): string {
  if (!stageLabel.trim()) return "";
  if (!scopeLabel || stageLabel === "Processing complete") return stageLabel;
  return `${scopeLabel}: ${stageLabel}`;
}

function AgentStatusNode({ statusText, subText = null, isRunning = true }: AgentStatusNodeProps) {
  const hasStatusText = statusText.trim().length > 0;
  const hasSubText = (subText?.trim().length ?? 0) > 0;
  if (!hasStatusText && !hasSubText) return null;

  const stateClassName = isRunning ? styles.agentStatusLineRunning : styles.agentStatusLineDone;
  return (
    <div className={styles.agentStatusNode} aria-live="polite">
      {hasStatusText ? (
        <p className={`${styles.agentStatusLine} ${styles.agentStatusPrimary} ${stateClassName}`}>{statusText}</p>
      ) : null}
      {hasSubText ? (
        <p className={`${styles.agentStatusLine} ${styles.agentStatusSecondary} ${stateClassName}`}>{subText}</p>
      ) : null}
    </div>
  );
}

function toRelevanceLabel(score: number | null | undefined): string {
  if (typeof score !== "number" || Number.isNaN(score)) return "Medium relevance";
  if (score >= 0.75) return "High relevance";
  if (score >= 0.45) return "Medium relevance";
  return "Low relevance";
}

function sourceDisplayName(item: EvidenceItem): string {
  return item.document_title || item.document_filename || "Source";
}

type WorkspaceHeaderProps = {
  companyName: string;
  logoSrc: string | null;
  workspaceTitle: string;
  workspaceSubtitle?: string;
  onLogout?: () => void;
  isLoggingOut?: boolean;
};

export function WorkspaceHeader({
  companyName,
  logoSrc,
  workspaceTitle,
  workspaceSubtitle,
  onLogout,
  isLoggingOut = false,
}: WorkspaceHeaderProps) {
  return (
    <header className={styles.header}>
      <nav className={styles.navBar} aria-label="Workspace navigation">
        <div className={styles.brandBarIdentity}>
          {logoSrc ? (
            <img className={styles.logo} src={logoSrc} alt={`${companyName} logo`} />
          ) : (
            <span className={styles.logoFallback} aria-hidden="true">
              {companyName.slice(0, 1)}
            </span>
          )}
          <div className={styles.brandText}>
            <p className={styles.companyName}>{companyName}</p>
            <h1 className={styles.workspaceTitle}>{workspaceTitle}</h1>
            {workspaceSubtitle ? <p className={styles.workspaceSubtitle}>{workspaceSubtitle}</p> : null}
          </div>
        </div>
        {onLogout ? (
          <button type="button" className={styles.ghostButton} onClick={onLogout} disabled={isLoggingOut}>
            {isLoggingOut ? "Logging out..." : "Logout"}
          </button>
        ) : null}
      </nav>
    </header>
  );
}

type DocumentMetaPanelProps = {
  document: ResponseDocument | null;
  title: string;
  subtitle: string;
  loading: boolean;
  onUpload: () => void;
  onUseExamples: () => void;
  showExampleQuestions?: boolean;
  showSourceFilename?: boolean;
  exampleQuestionsButtonLabel?: string;
};

export function DocumentMetaPanel({
  document,
  title,
  subtitle,
  loading,
  onUpload,
  onUseExamples,
  showExampleQuestions = true,
  showSourceFilename = true,
  exampleQuestionsButtonLabel = "Use example questions",
}: DocumentMetaPanelProps) {
  if (!document) {
    return (
      <section className={styles.startState}>
        <div className={styles.startCard}>
          <h2>{title}</h2>
          <p>{subtitle}</p>
          <div className={styles.startActions}>
            <button type="button" onClick={onUpload} disabled={loading}>
              Upload document
            </button>
            {showExampleQuestions ? (
              <button type="button" className={styles.secondaryButton} onClick={onUseExamples} disabled={loading}>
                {exampleQuestionsButtonLabel}
              </button>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.documentHeader}>
      <div>
        <h2>{document.title || "Response draft"}</h2>
        <p className={styles.questionMeta}>
          {document.questions.length} questions
          {showSourceFilename && document.source_filename ? ` · Source: ${document.source_filename}` : ""}
        </p>
      </div>
    </section>
  );
}

type GenerateCardProps = {
  generating: boolean;
  loading: boolean;
  onGenerate: () => void;
};

export function GenerateCard({ generating, loading, onGenerate }: GenerateCardProps) {
  return (
    <section className={styles.centerCard}>
      <h3>Generate a complete draft document</h3>
      <p>Generate answers for all loaded questions in one pass.</p>
      <button
        type="button"
        className={styles.centerCardAction}
        onClick={onGenerate}
        disabled={loading || generating}
      >
        {generating ? "Generating..." : "Generate draft"}
      </button>
    </section>
  );
}

type StageCardProps = {
  title: string;
  stages: Stage[];
  scopeLabel?: string | null;
};

export function StageCard({ title, stages, scopeLabel = null }: StageCardProps) {
  const currentStage = activeStageLabel(stages);
  const tickerLabel = stageTickerLabel(currentStage, scopeLabel);
  const isComplete = stages.length > 0 && stages.every((stage) => stage.status === "done");
  return (
    <section className={styles.centerCard}>
      <div className={styles.processingHeader}>
        <span className={isComplete ? styles.processingDoneDot : styles.runSpinner} aria-hidden="true" />
        <AgentStatusNode statusText={title} subText={tickerLabel} isRunning={!isComplete} />
      </div>
    </section>
  );
}

type ProcessingStatusStripProps = {
  title: string;
  stages: Stage[];
  isRunning: boolean;
  scopeLabel?: string | null;
};

export function ProcessingStatusStrip({
  title,
  stages,
  isRunning,
  scopeLabel = null,
}: ProcessingStatusStripProps) {
  const currentStage = activeStageLabel(stages);
  const runningLabel = stageTickerLabel(currentStage, scopeLabel);
  const processingLabel = isRunning ? runningLabel : "Processing complete";
  return (
    <section className={styles.processingStrip}>
      <div className={styles.processingStripLead}>
        <span
          className={isRunning ? styles.runSpinner : styles.processingDoneDot}
          aria-hidden="true"
        />
        <AgentStatusNode statusText={title} subText={processingLabel} isRunning={isRunning} />
      </div>
      <p className={styles.processingStripState}>{isRunning ? "In progress" : "Completed"}</p>
    </section>
  );
}

type AIComposerProps = {
  instruction: string;
  askingAi: boolean;
  loading: boolean;
  mode?: "default" | "overlay";
  scope: "selected_question" | "whole_document";
  allowQuestionScope?: boolean;
  allowWholeDocumentScope?: boolean;
  helperText?: string;
  submitButtonLabel?: string;
  questions: Array<{ id: string; label: string }>;
  selectedQuestionId: string | null;
  onInstructionChange: (value: string) => void;
  onScopeChange: (value: "selected_question" | "whole_document") => void;
  onQuestionChange: (value: string) => void;
  onApply: () => void;
  onCancel: () => void;
};

export function AIComposer({
  instruction,
  askingAi,
  loading,
  mode = "default",
  scope,
  allowQuestionScope = true,
  allowWholeDocumentScope = true,
  helperText = "Agent will plan and apply edits for the selected scope.",
  submitButtonLabel = "Submit",
  questions,
  selectedQuestionId,
  onInstructionChange,
  onScopeChange,
  onQuestionChange,
  onApply,
  onCancel,
}: AIComposerProps) {
  const hasQuestions = questions.length > 0;
  const availableScopes: Array<"selected_question" | "whole_document"> = [];
  if (allowQuestionScope) availableScopes.push("selected_question");
  if (allowWholeDocumentScope) availableScopes.push("whole_document");
  if (!availableScopes.length) {
    availableScopes.push("selected_question");
  }
  const selectedScope = availableScopes.includes(scope) ? scope : availableScopes[0];
  const composerClassName =
    mode === "overlay" ? `${styles.aiComposer} ${styles.aiComposerOverlay}` : styles.aiComposer;
  return (
    <section className={composerClassName}>
      <p className={styles.sectionLabel}>Suggest changes</p>
      {availableScopes.length > 1 ? (
        <>
          <label htmlFor="revision-scope" className={styles.fieldLabel}>
            Scope
          </label>
          <select
            id="revision-scope"
            value={selectedScope}
            onChange={(event) => onScopeChange(event.target.value as "selected_question" | "whole_document")}
            disabled={askingAi || loading}
          >
            {allowQuestionScope ? <option value="selected_question">Selected question</option> : null}
            {allowWholeDocumentScope ? <option value="whole_document">Whole document</option> : null}
          </select>
        </>
      ) : null}
      <p className={styles.questionMeta}>{helperText}</p>
      {selectedScope === "selected_question" ? (
        <>
          <label htmlFor="revision-question" className={styles.fieldLabel}>
            Question
          </label>
          <select
            id="revision-question"
            value={selectedQuestionId ?? ""}
            onChange={(event) => onQuestionChange(event.target.value)}
            disabled={askingAi || loading || !hasQuestions}
          >
            {questions.map((question, index) => (
              <option key={question.id} value={question.id}>
                {index + 1}. {question.label}
              </option>
            ))}
          </select>
        </>
      ) : null}
      <label htmlFor="ai-instruction" className={styles.fieldLabel}>
        Instructions
      </label>
      <textarea
        id="ai-instruction"
        value={instruction}
        onChange={(event) => onInstructionChange(event.target.value)}
        rows={3}
        placeholder="Describe what should change..."
      />
      <div className={styles.aiActions}>
        <button type="button" onClick={onApply} disabled={askingAi || loading}>
          {askingAi ? "Applying..." : submitButtonLabel}
        </button>
        <button type="button" className={styles.secondaryButton} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}

type EditorSurfaceProps = {
  questions: ResponseDocument["questions"];
  sectionsByQuestionId: Record<string, ResponseSection | undefined>;
  editableSections: Record<string, string>;
  hasUnsavedChanges: boolean;
  globalNotice: string | null;
  onSectionChange: (questionId: string, value: string) => void;
  onSectionFocus?: (questionId: string) => void;
};

export function EditorSurface({
  questions,
  sectionsByQuestionId,
  editableSections,
  hasUnsavedChanges,
  globalNotice,
  onSectionChange,
  onSectionFocus,
}: EditorSurfaceProps) {
  const [expandedSourcesByQuestionId, setExpandedSourcesByQuestionId] = useState<Record<string, boolean>>({});

  function toggleSources(questionId: string): void {
    setExpandedSourcesByQuestionId((previous) => ({
      ...previous,
      [questionId]: !previous[questionId],
    }));
  }

  return (
    <section className={styles.editorSurface}>
      {hasUnsavedChanges ? <p className={styles.unsavedBadge}>Unsaved changes</p> : null}
      {globalNotice ? <p className={styles.globalNotice}>{globalNotice}</p> : null}
      {questions.map((question, index) => {
        const section = sectionsByQuestionId[question.id];
        const sources = section?.evidence_refs ?? [];
        const isExpanded = !!expandedSourcesByQuestionId[question.id];
        return (
          <article key={question.id} className={styles.sectionCard}>
            <h3>
              {index + 1}. {question.extracted_text}
            </h3>
            <textarea
              value={editableSections[question.id] ?? ""}
              onChange={(event) => onSectionChange(question.id, event.target.value)}
              onFocus={() => onSectionFocus?.(question.id)}
              rows={8}
            />
            <div className={styles.supportingSources}>
              <button
                type="button"
                className={styles.showSourcesButton}
                onClick={() => toggleSources(question.id)}
              >
                {isExpanded ? "Hide sources" : `Sources (${sources.length})`}
              </button>
              {isExpanded ? (
                <div className={styles.supportingSourcesPanel}>
                  {!sources.length ? (
                    <p className={styles.questionMeta}>No supporting sources available for this response.</p>
                  ) : null}
                  {sources.map((item, sourceIndex) => (
                    <article
                      key={`${question.id}-${item.chunk_id}-${item.chunk_index}`}
                      className={styles.sourceRow}
                    >
                  <p className={styles.sourceMeta}>
                    <span className={styles.sourceIndex}>[{sourceIndex + 1}]</span>{" "}
                    <span>{toRelevanceLabel(item.score)}</span>
                    {typeof item.score === "number" ? <span className={styles.sourceScore}> · {item.score.toFixed(2)}</span> : null}
                    <span className={styles.sourceSeparator}> · </span>
                    <span className={styles.sourceTitle}>{sourceDisplayName(item)}</span>
                  </p>
                      <p className={styles.sourceExcerpt}>{item.text}</p>
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          </article>
        );
      })}
    </section>
  );
}

type GeneratingDraftPreviewProps = {
  questions: ResponseDocument["questions"];
  sectionsByQuestionId: Record<string, string>;
  evidenceByQuestionId: Record<string, EvidenceItem[]>;
};

export function GeneratingDraftPreview({
  questions,
  sectionsByQuestionId,
  evidenceByQuestionId,
}: GeneratingDraftPreviewProps) {
  const [expandedSourcesByQuestionId, setExpandedSourcesByQuestionId] = useState<Record<string, boolean>>({});

  function toggleSources(questionId: string): void {
    setExpandedSourcesByQuestionId((previous) => ({
      ...previous,
      [questionId]: !previous[questionId],
    }));
  }

  return (
    <section className={styles.editorSurface}>
      {questions.map((question, index) => {
        const sources = evidenceByQuestionId[question.id] ?? [];
        const isExpanded = !!expandedSourcesByQuestionId[question.id];
        return (
          <article key={question.id} className={styles.sectionCard}>
            <h3>
              {index + 1}. {question.extracted_text}
            </h3>
            <textarea
              value={sectionsByQuestionId[question.id] ?? ""}
              rows={8}
              readOnly
              aria-label={`Draft answer for question ${index + 1}`}
              placeholder="Generating response..."
            />
            <div className={styles.supportingSources}>
              <button
                type="button"
                className={styles.showSourcesButton}
                onClick={() => toggleSources(question.id)}
              >
                {isExpanded ? "Hide sources" : `Sources (${sources.length})`}
              </button>
              {isExpanded ? (
                <div className={styles.supportingSourcesPanel}>
                  {!sources.length ? (
                    <p className={styles.questionMeta}>No supporting sources available for this response.</p>
                  ) : null}
                  {sources.map((item, sourceIndex) => (
                    <article
                      key={`${question.id}-${item.chunk_id}-${item.chunk_index}`}
                      className={styles.sourceRow}
                    >
                      <p className={styles.sourceMeta}>
                        <span className={styles.sourceIndex}>[{sourceIndex + 1}]</span>{" "}
                        <span>{toRelevanceLabel(item.score)}</span>
                        {typeof item.score === "number" ? <span className={styles.sourceScore}> · {item.score.toFixed(2)}</span> : null}
                        <span className={styles.sourceSeparator}> · </span>
                        <span className={styles.sourceTitle}>{sourceDisplayName(item)}</span>
                      </p>
                      <p className={styles.sourceExcerpt}>{item.text}</p>
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          </article>
        );
      })}
    </section>
  );
}

type VersionRowProps = {
  versions: ResponseVersionSummary[];
  selectedVersionId: string;
  loading: boolean;
  onSelect: (versionId: string) => void;
  onDelete: (version: ResponseVersionSummary) => void;
};

export function VersionRow({
  versions,
  selectedVersionId,
  loading,
  onSelect,
  onDelete,
}: VersionRowProps) {
  return (
    <section className={styles.versionRow}>
      <div className={styles.versionTabs}>
        {versions.map((version) => (
          <div key={version.id} className={styles.versionTabWrap}>
            <button
              type="button"
              className={version.id === selectedVersionId ? styles.versionTabActive : styles.versionTab}
              onClick={() => onSelect(version.id)}
              disabled={loading}
            >
              Version {version.version_number}
            </button>
            {version.id === selectedVersionId && versions.length > 1 ? (
              <button
                type="button"
                className={styles.versionDeleteInline}
                onClick={() => onDelete(version)}
                disabled={loading}
                aria-label={`Delete Version ${version.version_number}`}
              >
                ×
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function segmentClass(kind: DraftDiffSegment["kind"]): string {
  if (kind === "added") return styles.diffAdded;
  if (kind === "removed") return styles.diffRemoved;
  return styles.diffSame;
}

type ComparePanelProps = {
  compareData: ResponseVersionComparison;
  versions: ResponseDocument["versions"];
  leftVersionId: string | null;
  rightVersionId: string | null;
  onLeftChange: (value: string) => void;
  onRightChange: (value: string) => void;
  onRefresh: () => void;
};

export function ComparePanel({
  compareData,
  versions,
  leftVersionId,
  rightVersionId,
  onLeftChange,
  onRightChange,
  onRefresh,
}: ComparePanelProps) {
  return (
    <section className={styles.comparePanel}>
      <div className={styles.compareHeader}>
        <h3>Version comparison</h3>
        <div className={styles.compareSelectors}>
          <select value={leftVersionId ?? ""} onChange={(event) => onLeftChange(event.target.value)}>
            {versions.map((version) => (
              <option key={`left-${version.id}`} value={version.id}>
                Left: Version {version.version_number}
              </option>
            ))}
          </select>
          <select value={rightVersionId ?? ""} onChange={(event) => onRightChange(event.target.value)}>
            {versions.map((version) => (
              <option key={`right-${version.id}`} value={version.id}>
                Right: Version {version.version_number}
              </option>
            ))}
          </select>
          <button type="button" className={styles.secondaryButton} onClick={onRefresh}>
            Refresh
          </button>
        </div>
      </div>
      <div className={styles.diffBlock}>
        {compareData.section_diffs.map((sectionDiff) => (
          <div key={sectionDiff.question_id} className={styles.diffSection}>
            <p className={styles.diffHeading}>{sectionDiff.question_text}</p>
            <p className={styles.diffText}>
              {sectionDiff.segments.map((segment, index) => (
                <span key={`${sectionDiff.question_id}-${index}`} className={segmentClass(segment.kind)}>
                  {segment.text}
                </span>
              ))}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

type ActivityPanelProps = {
  title: string;
  subtitle: string;
  stages: Stage[];
  isRunning: boolean;
  hasRunHistory: boolean;
};

export function ActivityPanel({
  title,
  subtitle,
  stages,
  isRunning,
  hasRunHistory,
}: ActivityPanelProps) {
  return (
    <section className={styles.sidePanel}>
      <h3>Activity</h3>
      <p className={styles.questionMeta}>
        {hasRunHistory ? subtitle : "Run generation or submit a revision to view processing activity."}
      </p>
      {hasRunHistory ? (
        <>
          <div className={styles.processingStripLead}>
            <span
              className={isRunning ? styles.runSpinner : styles.processingDoneDot}
              aria-hidden="true"
            />
            <p className={styles.processingStripTitle}>{title}</p>
          </div>
          <div className={styles.stageList}>
            {stages.map((stage) => (
              <p key={`activity-${stage.label}`} className={`${styles.stageRow} ${styles[`stage_${stage.status}`]}`}>
                <span className={styles.stageDot} />
                <span>{stage.label}</span>
                <span className={styles.stageStateLabel}>{stageStatusLabel(stage.status)}</span>
              </p>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
