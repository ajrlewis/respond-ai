import { applyReviewWorkspaceBrandingOverride, type ReviewWorkspaceBranding } from "@/config/review-workspace";
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
