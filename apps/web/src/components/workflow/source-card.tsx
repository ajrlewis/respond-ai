import { type EvidenceItem } from "@/lib/api";
import { formatRetrievalMethod } from "@/lib/format";

type SourceCardProps = {
  item: EvidenceItem;
  sourceKey: string;
  citationNumber: number | undefined;
  isCitedChunk: boolean;
  isExcluded: boolean;
  isFocused: boolean;
  isApproved: boolean;
  isViewingHistoricalDraft: boolean;
  canUseWorkflowActions: boolean;
  loading: boolean;
  onToggleEvidenceExclusion: (key: string) => void;
  registerCardRef: (key: string, node: HTMLDivElement | null) => void;
};

export function SourceCard({
  item,
  sourceKey,
  citationNumber,
  isCitedChunk,
  isExcluded,
  isFocused,
  isApproved,
  isViewingHistoricalDraft,
  canUseWorkflowActions,
  loading,
  onToggleEvidenceExclusion,
  registerCardRef,
}: SourceCardProps) {
  const badgeLabel = citationNumber
    ? `[${citationNumber}]`
    : isExcluded
      ? "Excluded from revision"
      : isApproved
        ? "Not used in final answer"
        : isViewingHistoricalDraft
          ? "Not used in selected draft"
          : "Not used in current draft";

  return (
    <div
      ref={(node) => registerCardRef(sourceKey, node)}
      className={`evidence-card${isCitedChunk ? " evidence-card-cited" : " evidence-card-uncited"}${
        isExcluded ? " evidence-card-excluded" : ""
      }${isFocused ? " evidence-card-focused" : ""}`}
    >
      <div className="evidence-title-row">
        <span className={`citation-badge${isCitedChunk ? " cited" : " uncited"}`}>{badgeLabel}</span>
        <span className="evidence-document">{item.document_filename}</span>
      </div>
      <p>{item.text}</p>
      <div className="evidence-detail-row">
        <span>
          Chunk {item.chunk_index} · {formatRetrievalMethod(item.retrieval_method)} · Score: {item.score.toFixed(2)}
        </span>
      </div>
      {canUseWorkflowActions && (
        <div className="evidence-footer">
          <button
            type="button"
            className={`source-toggle${isExcluded ? " active" : ""}`}
            onClick={() => onToggleEvidenceExclusion(sourceKey)}
            disabled={loading}
          >
            {isExcluded ? "Include in next revision" : "Exclude in next revision"}
          </button>
        </div>
      )}
    </div>
  );
}
