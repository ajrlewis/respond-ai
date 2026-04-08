import { type EvidenceItem, type ResponseDocument } from "@/lib/api";

export type Stage = {
  label: string;
  status: "idle" | "running" | "done";
};

export function updateStagesFromServer(
  stages: Stage[],
  stageLabel: string,
  status: "running" | "done",
): Stage[] {
  const trimmedLabel = stageLabel.trim();
  if (!trimmedLabel) return stages;

  const next = [...stages];
  let targetIndex = next.findIndex((stage) => stage.label === trimmedLabel);
  if (targetIndex < 0) {
    next.push({ label: trimmedLabel, status: "idle" });
    targetIndex = next.length - 1;
  }

  if (status === "running") {
    return next.map((stage, index) => {
      if (index < targetIndex) return { ...stage, status: "done" };
      if (index === targetIndex) return { ...stage, status: "running" };
      return { ...stage, status: "idle" };
    });
  }

  return next.map((stage, index) => {
    if (index <= targetIndex) return { ...stage, status: "done" };
    return { ...stage, status: "idle" };
  });
}

export function markAllStagesDone(stages: Stage[]): Stage[] {
  return stages.map((stage) => ({ ...stage, status: "done" }));
}

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

const INLINE_CITATION_PATTERN = /\[(\d+)\]/g;

export type SyncedSectionContent = {
  contentMarkdown: string;
  evidenceRefs: EvidenceItem[];
};

function extractOrderedCitationNumbers(contentMarkdown: string): number[] {
  const ordered: number[] = [];
  const seen = new Set<number>();
  for (const match of contentMarkdown.matchAll(INLINE_CITATION_PATTERN)) {
    const parsed = Number.parseInt(match[1] ?? "", 10);
    if (!Number.isFinite(parsed) || parsed <= 0 || seen.has(parsed)) continue;
    ordered.push(parsed);
    seen.add(parsed);
  }
  return ordered;
}

export function syncSectionContentAndEvidence(
  contentMarkdown: string,
  evidenceRefs: EvidenceItem[],
): SyncedSectionContent {
  if (!contentMarkdown.trim() || !evidenceRefs.length) {
    return {
      contentMarkdown,
      evidenceRefs: [],
    };
  }

  const orderedCitations = extractOrderedCitationNumbers(contentMarkdown).filter(
    (citationNumber) => citationNumber >= 1 && citationNumber <= evidenceRefs.length,
  );
  if (!orderedCitations.length) {
    return {
      contentMarkdown,
      evidenceRefs: [],
    };
  }

  const renumberMap = new Map<number, number>();
  orderedCitations.forEach((sourceCitation, index) => {
    renumberMap.set(sourceCitation, index + 1);
  });
  const normalizedContent = contentMarkdown.replace(INLINE_CITATION_PATTERN, (fullMatch, raw) => {
    const current = Number.parseInt(raw, 10);
    const mapped = renumberMap.get(current);
    if (!mapped) return fullMatch;
    return `[${mapped}]`;
  });

  return {
    contentMarkdown: normalizedContent,
    evidenceRefs: orderedCitations
      .map((citationNumber) => evidenceRefs[citationNumber - 1])
      .filter((item): item is EvidenceItem => !!item),
  };
}
