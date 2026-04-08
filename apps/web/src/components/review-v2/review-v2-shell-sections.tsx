import { type AnswerVersion } from "@/lib/api";

import { ReviewV2Document } from "@/components/review-v2/review-v2-document";
import { type UseWorkflowResult } from "@/hooks/use-workflow";

type SummaryMetric = {
  label: string;
  value: string;
  muted?: boolean;
};

type WorkspaceHeaderProps = {
  companyName: string;
  logoSrc: string | null;
  workspaceTitle: string;
  workspaceSubtitle: string;
  onLogout?: () => void;
  isLoggingOut?: boolean;
  headerClassName: string;
  brandRowClassName: string;
  logoClassName: string;
  logoFallbackClassName: string;
  companyNameClassName: string;
  workspaceSubtitleClassName: string;
  ghostButtonClassName: string;
};

export function WorkspaceHeader({
  companyName,
  logoSrc,
  workspaceTitle,
  workspaceSubtitle,
  onLogout,
  isLoggingOut = false,
  headerClassName,
  brandRowClassName,
  logoClassName,
  logoFallbackClassName,
  companyNameClassName,
  workspaceSubtitleClassName,
  ghostButtonClassName,
}: WorkspaceHeaderProps) {
  return (
    <header className={headerClassName}>
      <div className={brandRowClassName}>
        {logoSrc ? (
          <img className={logoClassName} src={logoSrc} alt={`${companyName} logo`} />
        ) : (
          <span className={logoFallbackClassName} aria-hidden="true">
            {companyName.slice(0, 1)}
          </span>
        )}
        <div>
          <p className={companyNameClassName}>{companyName}</p>
          <h1>{workspaceTitle}</h1>
          <p className={workspaceSubtitleClassName}>{workspaceSubtitle}</p>
        </div>
      </div>

      {onLogout ? (
        <button
          type="button"
          className={ghostButtonClassName}
          onClick={onLogout}
          disabled={isLoggingOut}
        >
          {isLoggingOut ? "Logging out..." : "Logout"}
        </button>
      ) : null}
    </header>
  );
}

type StartSectionProps = {
  title: string;
  subtitle: string;
  onUpload: () => void;
  onUseExamples: () => void;
  secondaryButtonClassName: string;
  startStateClassName: string;
  startCardClassName: string;
  startActionsClassName: string;
};

export function StartSection({
  title,
  subtitle,
  onUpload,
  onUseExamples,
  secondaryButtonClassName,
  startStateClassName,
  startCardClassName,
  startActionsClassName,
}: StartSectionProps) {
  return (
    <section className={startStateClassName}>
      <div className={startCardClassName}>
        <h2>{title}</h2>
        <p>{subtitle}</p>
        <div className={startActionsClassName}>
          <button type="button" onClick={onUpload}>
            Upload document
          </button>
          <button type="button" className={secondaryButtonClassName} onClick={onUseExamples}>
            Use example questions
          </button>
        </div>
      </div>
    </section>
  );
}

type QuestionSectionProps = {
  activeQuestion: string;
  uploadedDocumentName: string | null;
  summaryMetrics: SummaryMetric[];
  showGenerate: boolean;
  loading: boolean;
  canGenerate: boolean;
  onGenerate: () => void;
  questionSectionClassName: string;
  questionBodyClassName: string;
  sectionLabelClassName: string;
  questionMetaClassName: string;
  questionMetricsClassName: string;
  summaryMetricClassName: string;
  summaryMetricMutedClassName: string;
};

export function QuestionSection({
  activeQuestion,
  uploadedDocumentName,
  summaryMetrics,
  showGenerate,
  loading,
  canGenerate,
  onGenerate,
  questionSectionClassName,
  questionBodyClassName,
  sectionLabelClassName,
  questionMetaClassName,
  questionMetricsClassName,
  summaryMetricClassName,
  summaryMetricMutedClassName,
}: QuestionSectionProps) {
  return (
    <section className={questionSectionClassName}>
      <div className={questionBodyClassName}>
        <p className={sectionLabelClassName}>Current question</p>
        <h2>{activeQuestion || "Select a question to continue."}</h2>
        {uploadedDocumentName ? <p className={questionMetaClassName}>Source: {uploadedDocumentName}</p> : null}
        {summaryMetrics.length ? (
          <div className={questionMetricsClassName}>
            {summaryMetrics.map((metric) => (
              <p
                key={metric.label}
                className={
                  metric.muted
                    ? `${summaryMetricClassName} ${summaryMetricMutedClassName}`
                    : summaryMetricClassName
                }
              >
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </p>
            ))}
          </div>
        ) : null}
      </div>

      {showGenerate ? (
        <button type="button" onClick={onGenerate} disabled={!canGenerate || loading}>
          {loading ? "Starting..." : "Generate draft"}
        </button>
      ) : null}
    </section>
  );
}

type QuestionTabsProps = {
  questionSet: string[];
  selectedQuestionIndex: number;
  onSelectQuestion: (index: number) => void;
  questionTabsClassName: string;
  activeTabClassName: string;
  tabClassName: string;
};

export function QuestionTabs({
  questionSet,
  selectedQuestionIndex,
  onSelectQuestion,
  questionTabsClassName,
  activeTabClassName,
  tabClassName,
}: QuestionTabsProps) {
  if (questionSet.length <= 1) return null;

  return (
    <section className={questionTabsClassName}>
      {questionSet.map((_, index) => (
        <button
          key={`question-${index}`}
          type="button"
          className={index === selectedQuestionIndex ? activeTabClassName : tabClassName}
          onClick={() => onSelectQuestion(index)}
        >
          Q{index + 1}
        </button>
      ))}
    </section>
  );
}

type GeneratingSectionProps = {
  title: string;
  progressText: string;
  stages: { id: string; label: string; status: string }[];
  generatingStateClassName: string;
  loaderRowClassName: string;
  loaderDotClassName: string;
  stageListClassName: string;
  stageRowClassName: string;
  stageMarkerClassName: string;
  stageClassByStatus: Record<string, string>;
};

export function GeneratingSection({
  title,
  progressText,
  stages,
  generatingStateClassName,
  loaderRowClassName,
  loaderDotClassName,
  stageListClassName,
  stageRowClassName,
  stageMarkerClassName,
  stageClassByStatus,
}: GeneratingSectionProps) {
  return (
    <section className={generatingStateClassName}>
      <div className={loaderRowClassName}>
        <span className={loaderDotClassName} aria-hidden="true" />
        <div>
          <h3>{title}</h3>
          <p>{progressText}</p>
        </div>
      </div>
      <div className={stageListClassName}>
        {stages.map((stage) => (
          <div key={stage.id} className={`${stageRowClassName} ${stageClassByStatus[stage.status] || ""}`}>
            <span className={stageMarkerClassName} />
            <span>{stage.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

type ReviewingSectionProps = {
  drafts: AnswerVersion[];
  selectedDraftId: string | null;
  onSelectDraft: (draftId: string) => void;
  canApprove: boolean;
  canRevise: boolean;
  onApprove: () => void;
  onOpenRevise: () => void;
  onRegenerate: () => void;
  onExport: () => void;
  workflow: UseWorkflowResult;
  selectedVersionLabel: string;
  selectedVersionStatus: string;
  selectedDraftTimestamp: string;
  answerText: string;
  editableAnswerText: string;
  hasInlineEdits: boolean;
  isRevisionComposerOpen: boolean;
  inlineEditWarning: string | null;
  activeEvidenceKey: string | null;
  activeCitationNumber: number | null;
  citationKeyByNumber: Map<number, string>;
  onEditableAnswerTextChange: (value: string) => void;
  onRevisionFeedbackChange: (value: string) => void;
  onCancelRevision: () => void;
  onSubmitRevision: () => void;
  onCitationClick: (citationNumber: number, evidenceKey: string) => void;
  reviewControlsClassName: string;
  versionTabsClassName: string;
  versionTabClassName: string;
  versionTabActiveClassName: string;
  primaryActionsClassName: string;
  secondaryButtonClassName: string;
  moreMenuClassName: string;
  moreMenuTriggerClassName: string;
  moreMenuListClassName: string;
  moreMenuActionClassName: string;
  secondaryActionsClassName: string;
  ghostButtonClassName: string;
  onShowEvidence: () => void;
  onShowActivity: () => void;
};

export function ReviewingSection({
  drafts,
  selectedDraftId,
  onSelectDraft,
  canApprove,
  canRevise,
  onApprove,
  onOpenRevise,
  onRegenerate,
  onExport,
  workflow,
  selectedVersionLabel,
  selectedVersionStatus,
  selectedDraftTimestamp,
  answerText,
  editableAnswerText,
  hasInlineEdits,
  isRevisionComposerOpen,
  inlineEditWarning,
  activeEvidenceKey,
  activeCitationNumber,
  citationKeyByNumber,
  onEditableAnswerTextChange,
  onRevisionFeedbackChange,
  onCancelRevision,
  onSubmitRevision,
  onCitationClick,
  reviewControlsClassName,
  versionTabsClassName,
  versionTabClassName,
  versionTabActiveClassName,
  primaryActionsClassName,
  secondaryButtonClassName,
  moreMenuClassName,
  moreMenuTriggerClassName,
  moreMenuListClassName,
  moreMenuActionClassName,
  secondaryActionsClassName,
  ghostButtonClassName,
  onShowEvidence,
  onShowActivity,
}: ReviewingSectionProps) {
  return (
    <>
      <section className={reviewControlsClassName}>
        <div className={versionTabsClassName}>
          {drafts.map((draft) => {
            const isActive = draft.version_id === selectedDraftId;
            return (
              <button
                key={draft.version_id}
                type="button"
                className={isActive ? versionTabActiveClassName : versionTabClassName}
                onClick={() => onSelectDraft(draft.version_id)}
              >
                Version {draft.version_number}
              </button>
            );
          })}
        </div>

        <div className={primaryActionsClassName}>
          <button type="button" onClick={onApprove} disabled={!canApprove}>
            Approve
          </button>
          <button
            type="button"
            className={secondaryButtonClassName}
            onClick={onOpenRevise}
            disabled={!canRevise}
          >
            Revise
          </button>
          <details className={moreMenuClassName}>
            <summary className={moreMenuTriggerClassName}>More</summary>
            <div className={moreMenuListClassName}>
              <button type="button" className={moreMenuActionClassName} onClick={onRegenerate}>
                Regenerate
              </button>
              <button type="button" className={moreMenuActionClassName} onClick={onExport}>
                Export
              </button>
            </div>
          </details>
        </div>
      </section>

      <section className={secondaryActionsClassName}>
        <button type="button" className={ghostButtonClassName} onClick={onShowEvidence}>
          Show evidence
        </button>
        <button type="button" className={ghostButtonClassName} onClick={onShowActivity}>
          View activity
        </button>
      </section>

      <ReviewV2Document
        workflow={workflow}
        sessionStatus={workflow.session?.status ?? null}
        selectedVersionLabel={selectedVersionLabel}
        selectedVersionStatus={selectedVersionStatus}
        selectedDraftTimestamp={selectedDraftTimestamp}
        answerText={answerText}
        editableAnswerText={editableAnswerText}
        canEdit={canRevise}
        hasInlineEdits={hasInlineEdits}
        isRevisionComposerOpen={isRevisionComposerOpen}
        inlineEditWarning={inlineEditWarning}
        activeEvidenceKey={activeEvidenceKey}
        activeCitationNumber={activeCitationNumber}
        citationKeyByNumber={citationKeyByNumber}
        excludedEvidenceCount={workflow.excludedEvidenceKeys.size}
        revisionFeedback={workflow.feedback}
        revisionProgress={workflow.revisionProgress}
        isSubmittingRevision={workflow.isSubmittingRevision}
        error={workflow.error}
        onEditableAnswerTextChange={onEditableAnswerTextChange}
        onRevisionFeedbackChange={onRevisionFeedbackChange}
        onCancelRevision={onCancelRevision}
        onSubmitRevision={onSubmitRevision}
        onCitationClick={onCitationClick}
      />
    </>
  );
}
