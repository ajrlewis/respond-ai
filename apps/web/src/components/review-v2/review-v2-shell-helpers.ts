import { type ResponseDocument } from "@/lib/api";

export type Stage = {
  label: string;
  status: "idle" | "running" | "done";
};

export const GENERATION_STAGE_LABELS = [
  "Retrieve supporting material",
  "Rank evidence",
  "Draft response sections",
  "Review citations",
];

export const AI_STAGE_LABELS = [
  "Analyze revision request",
  "Revise draft text",
  "Prepare editable suggestions",
];

export const INSUFFICIENT_EVIDENCE_WARNING =
  "Insufficient internal evidence was retrieved to confidently draft a response. Please add internal material before finalizing this answer.";

export function emptyStages(labels: string[]): Stage[] {
  return labels.map((label) => ({ label, status: "idle" }));
}

export function toQuestionContentMap(document: ResponseDocument): Record<string, string> {
  const selected = document.selected_version;
  const byQuestion: Record<string, string> = {};
  if (selected) {
    for (const section of selected.sections) {
      byQuestion[section.question_id] = section.content_markdown;
    }
  }

  for (const question of document.questions) {
    if (!(question.id in byQuestion)) byQuestion[question.id] = "";
  }
  return byQuestion;
}

export function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "N/A";
  return `${Math.round(value * 100)}%`;
}

export function average(values: Array<number | null>): number | null {
  const filtered = values.filter((value): value is number => value !== null);
  if (!filtered.length) return null;
  return filtered.reduce((sum, value) => sum + value, 0) / filtered.length;
}

export function hasGlobalInsufficientEvidenceWarning(document: ResponseDocument): boolean {
  const sections = document.selected_version?.sections ?? [];
  if (!sections.length) return false;
  return sections.every(
    (section) => section.content_markdown.trim() === INSUFFICIENT_EVIDENCE_WARNING,
  );
}
