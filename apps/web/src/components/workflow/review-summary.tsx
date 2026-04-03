import { type Session } from "@/lib/api";

import { DisclosurePanel } from "@/components/workflow/disclosure-panel";

type ReviewSummaryProps = {
  confidenceScore: number | null;
  complianceSummary: string;
  evidenceGapCount: number;
  citationCount: number;
  confidenceNotes: string | null;
  evidenceCount: number;
  confidence: Session["confidence"];
  expanded: boolean;
  onToggle: () => void;
};

export function ReviewSummary({
  confidenceScore,
  complianceSummary,
  evidenceGapCount,
  citationCount,
  confidenceNotes,
  evidenceCount,
  confidence,
  expanded,
  onToggle,
}: ReviewSummaryProps) {
  return (
    <DisclosurePanel
      title="Review summary"
      summary={`Confidence: ${confidenceScore !== null ? confidenceScore.toFixed(2) : "N/A"} · Compliance: ${complianceSummary} · ${evidenceGapCount} evidence gap${
        evidenceGapCount === 1 ? "" : "s"
      } · ${citationCount} citation${citationCount === 1 ? "" : "s"}`}
      expanded={expanded}
      onToggle={onToggle}
      showLabel="View details"
      hideLabel="Hide details"
    >
      <p>{confidenceNotes || "No confidence notes available."}</p>
      <div className="confidence-summary-row">
        <span>Heuristic confidence: {confidence.score !== null ? confidence.score.toFixed(2) : "N/A"}</span>
        <span>Compliance: {complianceSummary}</span>
        <span>
          Evidence coverage: {citationCount}/{evidenceCount} cited chunks
        </span>
        {confidence.retrieval_strategy ? <span>Retrieval strategy: {confidence.retrieval_strategy}</span> : null}
        {confidence.coverage && confidence.coverage !== "unknown" ? <span>Evaluator coverage: {confidence.coverage}</span> : null}
      </div>
      <div className="review-notes-block">
        <p>
          <strong>Model notes:</strong> {confidence.model_notes || "No model notes provided."}
        </p>
        <p>
          <strong>Retrieval notes:</strong> {confidence.retrieval_notes || "No retrieval notes provided."}
        </p>
        {confidence.recommended_action && confidence.recommended_action !== "unknown" ? (
          <p>
            <strong>Evaluator recommendation:</strong> {confidence.recommended_action}
          </p>
        ) : null}
      </div>
    </DisclosurePanel>
  );
}
