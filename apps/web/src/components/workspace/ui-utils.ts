import { type Tone } from "@/lib/api";
import { type ParagraphReviewState, type RunStageStatus } from "@/lib/review-models";

export function stageStatusLabel(status: RunStageStatus): string {
  switch (status) {
    case "done":
      return "Done";
    case "running":
      return "Running";
    case "warning":
      return "Warning";
    case "failed":
      return "Failed";
    default:
      return "Idle";
  }
}

export function durationLabel(durationMs: number | null): string {
  if (durationMs === null) return "N/A";
  if (durationMs < 1000) return `${durationMs}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}

export function paragraphStateLabel(state: ParagraphReviewState): string {
  switch (state) {
    case "grounded":
      return "Grounded";
    case "weak_evidence":
      return "Weak evidence";
    case "changed_since_last_run":
      return "Changed";
    default:
      return "Unverified";
  }
}

export function toneLabel(tone: Tone): string {
  switch (tone) {
    case "concise":
      return "Concise";
    case "detailed":
      return "Detailed";
    default:
      return "Formal";
  }
}
