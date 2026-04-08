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
