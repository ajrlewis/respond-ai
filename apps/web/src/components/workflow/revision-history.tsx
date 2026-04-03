import { type AnswerVersion, type DraftDiffSegment } from "@/lib/api";
import { formatDraftTimestamp } from "@/lib/format";

import { DiffViewer } from "@/components/workflow/diff-viewer";
import { DisclosurePanel } from "@/components/workflow/disclosure-panel";

type RevisionHistoryProps = {
  drafts: AnswerVersion[];
  latestSnapshotTimestamp: string | null;
  selectedDraft: AnswerVersion | null;
  selectedDraftId: string | null;
  compareDraftId: string;
  compareEnabled: boolean;
  compareTargetDraft: AnswerVersion | null;
  compareSegments: DraftDiffSegment[];
  isViewingHistoricalDraft: boolean;
  isCompareMode: boolean;
  expanded: boolean;
  onToggle: () => void;
  onSelectDraft: (draftId: string | null) => void;
  onSelectCompareDraft: (draftId: string) => void;
};

export function RevisionHistory({
  drafts,
  latestSnapshotTimestamp,
  selectedDraft,
  selectedDraftId,
  compareDraftId,
  compareEnabled,
  compareTargetDraft,
  compareSegments,
  isViewingHistoricalDraft,
  isCompareMode,
  expanded,
  onToggle,
  onSelectDraft,
  onSelectCompareDraft,
}: RevisionHistoryProps) {
  return (
    <DisclosurePanel
      title="Revision history"
      summary={
        drafts.length
          ? `${drafts.length} draft version${drafts.length === 1 ? "" : "s"} · latest snapshot ${
              latestSnapshotTimestamp ? formatDraftTimestamp(latestSnapshotTimestamp) : "N/A"
            }`
          : "No draft versions yet."
      }
      expanded={expanded}
      onToggle={onToggle}
      showLabel="View history"
      hideLabel="Hide history"
    >
      {!drafts.length && <p className="placeholder">Draft history will appear after the first draft is generated.</p>}
      {!!drafts.length && (
        <>
          <div className="version-compare-row">
            <span>Viewing:</span>
            <select value={selectedDraftId ?? selectedDraft?.version_id ?? ""} onChange={(event) => onSelectDraft(event.target.value || null)}>
              {drafts.map((draft) => (
                <option key={draft.version_id} value={draft.version_id}>
                  {draft.label}
                </option>
              ))}
            </select>
          </div>
          <div className="version-compare-row">
            <span>Compare with:</span>
            <select value={compareEnabled ? compareDraftId : ""} onChange={(event) => onSelectCompareDraft(event.target.value)}>
              <option value="">Off</option>
              {drafts
                .filter((draft) => draft.version_id !== selectedDraft?.version_id)
                .map((draft) => (
                  <option key={draft.version_id} value={draft.version_id}>
                    {draft.label}
                  </option>
                ))}
            </select>
          </div>
          {(isViewingHistoricalDraft || isCompareMode) && (
            <p className="history-note">
              {isCompareMode
                ? "Comparison mode is read-only. Workflow actions apply only to the current latest draft."
                : "Viewing historical draft. Workflow actions apply only to the current latest draft."}
            </p>
          )}
          {isCompareMode && selectedDraft && (
            <DiffViewer
              leftLabel={compareTargetDraft?.label ?? "Draft"}
              rightLabel={selectedDraft.label}
              segments={compareSegments}
            />
          )}
        </>
      )}
    </DisclosurePanel>
  );
}
