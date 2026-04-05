import { type DraftDiffSegment } from "@/lib/api";

type DiffViewerProps = {
  leftLabel: string;
  rightLabel: string;
  segments: DraftDiffSegment[];
};

export function DiffViewer({ leftLabel, rightLabel, segments }: DiffViewerProps) {
  return (
    <div className="diff-view" aria-live="polite">
      <p className="version-meta">
        Diff: {leftLabel} vs {rightLabel}
      </p>
      {segments.length ? (
        segments.map((segment, index) => (
          <span key={`${segment.kind}-${index}-${segment.text}`} className={`diff-token diff-token-${segment.kind}`}>
            {segment.text}
          </span>
        ))
      ) : (
        <span className="diff-token diff-token-same">No differences available for this pair.</span>
      )}
    </div>
  );
}
