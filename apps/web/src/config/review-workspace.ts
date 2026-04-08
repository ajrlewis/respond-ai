export type ReviewWorkspaceBranding = {
  companyName: string;
  logoSrc: string | null;
  workspaceTitle: string;
  workspaceSubtitle: string;
  startTitle: string;
  startSubtitle: string;
};

function optionalString(value: string | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
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
