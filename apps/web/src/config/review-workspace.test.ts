import {
  applyReviewWorkspaceBrandingOverride,
  applyReviewWorkspaceSettingsOverride,
  reviewWorkspaceSettings,
  type ReviewWorkspaceBranding,
} from "@/config/review-workspace";
import { describe, expect, it } from "vitest";

const BASE: ReviewWorkspaceBranding = {
  companyName: "Base Co",
  logoSrc: null,
  workspaceTitle: "Base Workspace",
  workspaceSubtitle: "Base subtitle",
  startTitle: "Base start",
  startSubtitle: "Base start subtitle",
};

describe("applyReviewWorkspaceBrandingOverride", () => {
  it("applies branding override values from API payload", () => {
    const merged = applyReviewWorkspaceBrandingOverride(BASE, {
      company_name: "Gresham House",
      logo_url: "https://greshamhouse.com/logo.png",
      workspace_title: "Gresham House Response Workspace",
      workspace_subtitle: "Evidence-grounded drafting.",
      start_title: "Submission Workspace",
      start_subtitle: "Upload or use examples.",
    });

    expect(merged).toEqual({
      companyName: "Gresham House",
      logoSrc: "https://greshamhouse.com/logo.png",
      workspaceTitle: "Gresham House Response Workspace",
      workspaceSubtitle: "Evidence-grounded drafting.",
      startTitle: "Submission Workspace",
      startSubtitle: "Upload or use examples.",
    });
  });

  it("keeps base values when override payload is missing or invalid", () => {
    const merged = applyReviewWorkspaceBrandingOverride(BASE, {
      company_name: " ",
      logo_src: 42,
      workspace_title: "",
      start_subtitle: null,
    });

    expect(merged).toEqual(BASE);
  });
});

describe("applyReviewWorkspaceSettingsOverride", () => {
  it("maps ui flags and wording from workspace payload", () => {
    const merged = applyReviewWorkspaceSettingsOverride(reviewWorkspaceSettings, {
      ui_flags: {
        show_example_questions: false,
        show_source_filename: false,
        allow_question_scoped_revision: false,
        allow_full_document_revision: true,
      },
      approval_wording: {
        approve_button_label: "Approve Version",
        approve_helper_text: "Confirm this version is final.",
      },
      revision_wording: {
        submit_button_label: "Request Revision",
        revision_helper_text: "Describe precise, evidence-safe edits.",
        empty_feedback_error: "Add revision feedback before submitting.",
      },
    });

    expect(merged.uiFlags.showExampleQuestions).toBe(false);
    expect(merged.uiFlags.showSourceFilename).toBe(false);
    expect(merged.uiFlags.allowQuestionScopedRevision).toBe(false);
    expect(merged.uiFlags.allowFullDocumentRevision).toBe(true);
    expect(merged.approvalWording.approveButtonLabel).toBe("Approve Version");
    expect(merged.revisionWording.submitButtonLabel).toBe("Request Revision");
    expect(merged.revisionWording.emptyFeedbackError).toBe("Add revision feedback before submitting.");
  });

  it("keeps defaults for missing or invalid workspace keys", () => {
    const merged = applyReviewWorkspaceSettingsOverride(reviewWorkspaceSettings, {
      ui_flags: {
        show_example_questions: "no",
      },
      revision_wording: {
        submit_button_label: " ",
      },
    });

    expect(merged).toEqual(reviewWorkspaceSettings);
  });
});
