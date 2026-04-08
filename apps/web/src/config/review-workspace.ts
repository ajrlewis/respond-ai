export type ReviewWorkspaceBranding = {
  companyName: string;
  logoSrc: string | null;
  workspaceTitle: string;
  workspaceSubtitle: string;
  startTitle: string;
  startSubtitle: string;
};

export type ReviewWorkspaceBrandingOverride = {
  company_name?: unknown;
  logo_src?: unknown;
  logo_url?: unknown;
  logo_path?: unknown;
  workspace_title?: unknown;
  workspace_subtitle?: unknown;
  start_title?: unknown;
  start_subtitle?: unknown;
};

export type ReviewWorkspaceUiFlags = {
  showExampleQuestions: boolean;
  showSourceFilename: boolean;
  showConfidenceNotes: boolean;
  allowQuestionScopedRevision: boolean;
  allowFullDocumentRevision: boolean;
};

export type ReviewWorkspaceApprovalWording = {
  approveButtonLabel: string;
  approveHelperText: string;
};

export type ReviewWorkspaceRevisionWording = {
  submitButtonLabel: string;
  revisionHelperText: string;
  emptyFeedbackError: string;
};

export type ReviewWorkspaceSettings = {
  uiFlags: ReviewWorkspaceUiFlags;
  approvalWording: ReviewWorkspaceApprovalWording;
  revisionWording: ReviewWorkspaceRevisionWording;
};

function optionalString(value: string | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function optionalUnknownString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function readString(value: unknown, fallback: string): string {
  const candidate = optionalUnknownString(value);
  return candidate ?? fallback;
}

function readBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export const reviewWorkspaceBranding: ReviewWorkspaceBranding = {
  companyName: process.env.NEXT_PUBLIC_WORKSPACE_COMPANY_NAME?.trim() || "Acme Capital",
  logoSrc: optionalString(process.env.NEXT_PUBLIC_WORKSPACE_LOGO_SRC),
  workspaceTitle: process.env.NEXT_PUBLIC_WORKSPACE_TITLE?.trim() || "Response Workspace",
  workspaceSubtitle:
    process.env.NEXT_PUBLIC_WORKSPACE_SUBTITLE?.trim() ||
    "Document review workflow for submission responses.",
  startTitle: process.env.NEXT_PUBLIC_WORKSPACE_START_TITLE?.trim() || "Submission Workspace",
  startSubtitle:
    process.env.NEXT_PUBLIC_WORKSPACE_START_SUBTITLE?.trim() ||
    "Upload a questionnaire or start from example questions to generate a draft response.",
};

export const reviewWorkspaceSettings: ReviewWorkspaceSettings = {
  uiFlags: {
    showExampleQuestions: true,
    showSourceFilename: true,
    showConfidenceNotes: true,
    allowQuestionScopedRevision: true,
    allowFullDocumentRevision: true,
  },
  approvalWording: {
    approveButtonLabel: "Approve",
    approveHelperText: "Confirm this version is complete, evidence-grounded, and ready for final use.",
  },
  revisionWording: {
    submitButtonLabel: "Submit",
    revisionHelperText: "Agent will plan and apply edits for the selected scope.",
    emptyFeedbackError: "Describe changes before submitting.",
  },
};

export function applyReviewWorkspaceBrandingOverride(
  base: ReviewWorkspaceBranding,
  override?: ReviewWorkspaceBrandingOverride | null,
): ReviewWorkspaceBranding {
  if (!override) return base;

  return {
    companyName: readString(override.company_name, base.companyName),
    logoSrc:
      optionalUnknownString(override.logo_src)
      ?? optionalUnknownString(override.logo_url)
      ?? optionalUnknownString(override.logo_path)
      ?? base.logoSrc,
    workspaceTitle: readString(override.workspace_title, base.workspaceTitle),
    workspaceSubtitle: readString(override.workspace_subtitle, base.workspaceSubtitle),
    startTitle: readString(override.start_title, base.startTitle),
    startSubtitle: readString(override.start_subtitle, base.startSubtitle),
  };
}

export function applyReviewWorkspaceSettingsOverride(
  base: ReviewWorkspaceSettings,
  override?: unknown,
): ReviewWorkspaceSettings {
  const root = toRecord(override);
  const uiFlags = toRecord(root.ui_flags);
  const approvalWording = toRecord(root.approval_wording);
  const revisionWording = toRecord(root.revision_wording);

  return {
    uiFlags: {
      showExampleQuestions: readBoolean(uiFlags.show_example_questions, base.uiFlags.showExampleQuestions),
      showSourceFilename: readBoolean(uiFlags.show_source_filename, base.uiFlags.showSourceFilename),
      showConfidenceNotes: readBoolean(uiFlags.show_confidence_notes, base.uiFlags.showConfidenceNotes),
      allowQuestionScopedRevision: readBoolean(
        uiFlags.allow_question_scoped_revision,
        base.uiFlags.allowQuestionScopedRevision,
      ),
      allowFullDocumentRevision: readBoolean(
        uiFlags.allow_full_document_revision,
        base.uiFlags.allowFullDocumentRevision,
      ),
    },
    approvalWording: {
      approveButtonLabel: readString(
        approvalWording.approve_button_label,
        base.approvalWording.approveButtonLabel,
      ),
      approveHelperText: readString(
        approvalWording.approve_helper_text,
        base.approvalWording.approveHelperText,
      ),
    },
    revisionWording: {
      submitButtonLabel: readString(
        revisionWording.submit_button_label,
        base.revisionWording.submitButtonLabel,
      ),
      revisionHelperText: readString(
        revisionWording.revision_helper_text,
        base.revisionWording.revisionHelperText,
      ),
      emptyFeedbackError: readString(
        revisionWording.empty_feedback_error,
        base.revisionWording.emptyFeedbackError,
      ),
    },
  };
}
