export type ShellScreenState = "start" | "ready_to_generate" | "generating" | "reviewing";

export type StageLabel = {
  id: string;
  label: string;
  status: "idle" | "running" | "done" | "warning" | "failed";
};

export const STAGE_LABELS: Record<string, string> = {
  retrieve_context: "Retrieve supporting material",
  rank_evidence: "Rank evidence",
  draft_response: "Draft response",
  validate_grounding: "Review citations",
  review_confidence: "Check response quality",
  finalize_answer: "Finalize draft",
};

export function extractQuestions(raw: string): string[] {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .map((line) => line.replace(/^[-*\d.)\s]+/, "").trim())
    .filter((line) => line.length >= 12)
    .filter((line) => line.endsWith("?") || line.length >= 40);

  const unique = new Set<string>();
  for (const line of lines) {
    unique.add(line);
    if (unique.size >= 20) break;
  }

  return Array.from(unique);
}

export function fallbackStages(): StageLabel[] {
  return [
    { id: "retrieve_context", label: "Retrieve supporting material", status: "running" },
    { id: "rank_evidence", label: "Rank evidence", status: "idle" },
    { id: "draft_response", label: "Draft response", status: "idle" },
    { id: "validate_grounding", label: "Review citations", status: "idle" },
  ];
}
