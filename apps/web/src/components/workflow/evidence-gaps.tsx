import { DisclosurePanel } from "@/components/workflow/disclosure-panel";

type EvidenceGapsProps = {
  isApproved: boolean;
  hasEvidenceGaps: boolean;
  evidenceGapCount: number;
  evidenceGaps: string[];
  reviewedEvidenceGaps: boolean;
  expanded: boolean;
  onToggle: () => void;
  onReviewedEvidenceGapsChange: (checked: boolean) => void;
};

export function EvidenceGaps({
  isApproved,
  hasEvidenceGaps,
  evidenceGapCount,
  evidenceGaps,
  reviewedEvidenceGaps,
  expanded,
  onToggle,
  onReviewedEvidenceGapsChange,
}: EvidenceGapsProps) {
  if (!hasEvidenceGaps) {
    return (
      <section className="disclosure-card disclosure-card-success">
        <div className="disclosure-header disclosure-header-static">
          <div>
            <h3>Evidence gaps</h3>
            <p className="disclosure-summary-line">No outstanding evidence gaps.</p>
          </div>
          <span className="success-chip">Clear</span>
        </div>
      </section>
    );
  }

  return (
    <DisclosurePanel
      title="Evidence gaps"
      summary={`${evidenceGapCount} evidence gap${evidenceGapCount === 1 ? "" : "s"} · ${
        reviewedEvidenceGaps ? "Acknowledged" : "Needs review"
      }`}
      expanded={expanded}
      onToggle={onToggle}
      showLabel="Review"
      hideLabel="Collapse"
      tone="caution"
    >
      <div className="gaps-checklist">
        <ul>
          {evidenceGaps.map((gap) => (
            <li key={gap}>{gap}</li>
          ))}
        </ul>
        {!isApproved && (
          <label className="gap-ack">
            <input
              type="checkbox"
              checked={reviewedEvidenceGaps}
              onChange={(event) => onReviewedEvidenceGapsChange(event.target.checked)}
            />
            I have reviewed these evidence gaps and accept the remaining uncertainty.
          </label>
        )}
      </div>
    </DisclosurePanel>
  );
}
