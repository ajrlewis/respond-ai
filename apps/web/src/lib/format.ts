import { type AnswerVersion, type Session } from "@/lib/api";

function formatWords(value: string, fallback: string): string {
  const trimmed = value.trim();
  if (!trimmed) return fallback;

  return trimmed
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((word) => (word ? `${word[0].toUpperCase()}${word.slice(1)}` : word))
    .join(" ");
}

export function formatQuestionType(questionType: string | null): string {
  return questionType ? formatWords(questionType, "Unclassified") : "Unclassified";
}

export function formatComplianceStatus(status: Session["confidence"]["compliance_status"]): string {
  return formatWords(status, "Unknown");
}

export function formatDraftState(status: AnswerVersion["status"]): string {
  return formatWords(status, "Draft");
}

export function formatRetrievalMethod(method: string): string {
  const normalized = method.trim().toLowerCase();

  switch (normalized) {
    case "semantic":
      return "Semantic match";
    case "keyword":
      return "Keyword match";
    default:
      return method ? `${method[0].toUpperCase()}${method.slice(1)}` : "Unknown method";
  }
}

export function formatDraftTimestamp(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return timestamp;
  return parsed.toLocaleString();
}
