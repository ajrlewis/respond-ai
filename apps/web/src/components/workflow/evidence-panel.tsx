import { useEffect, useRef } from "react";

import { type EvidenceItem } from "@/lib/api";
import { evidenceKey } from "@/lib/workflow";

import { SourceCard } from "@/components/workflow/source-card";

type EvidencePanelProps = {
  evidence: EvidenceItem[];
  citationByEvidenceKey: Map<string, number>;
  citedEvidenceKeys: Set<string>;
  displayedExcludedEvidenceKeys: Set<string>;
  activeEvidenceKey: string | null;
  isApproved: boolean;
  isViewingHistoricalDraft: boolean;
  canUseWorkflowActions: boolean;
  loading: boolean;
  onToggleEvidenceExclusion: (key: string) => void;
};

export function EvidencePanel({
  evidence,
  citationByEvidenceKey,
  citedEvidenceKeys,
  displayedExcludedEvidenceKeys,
  activeEvidenceKey,
  isApproved,
  isViewingHistoricalDraft,
  canUseWorkflowActions,
  loading,
  onToggleEvidenceExclusion,
}: EvidencePanelProps) {
  const evidenceRefMap = useRef<Map<string, HTMLDivElement | null>>(new Map<string, HTMLDivElement | null>());

  useEffect(() => {
    if (!activeEvidenceKey) return;
    evidenceRefMap.current.get(activeEvidenceKey)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeEvidenceKey]);

  function registerEvidenceCardRef(key: string, node: HTMLDivElement | null) {
    evidenceRefMap.current.set(key, node);
  }

  return (
    <article className="glass-panel right-panel">
      <h2>Evidence & Citations</h2>
      <p className="panel-subtitle">Retrieved supporting chunks used to draft the response.</p>

      {!evidence.length && <p className="placeholder">Evidence will appear after retrieval.</p>}

      {evidence.map((item) => {
        const key = evidenceKey(item);

        return (
          <SourceCard
            key={item.chunk_id}
            item={item}
            sourceKey={key}
            citationNumber={citationByEvidenceKey.get(key)}
            isCitedChunk={citedEvidenceKeys.has(key)}
            isExcluded={displayedExcludedEvidenceKeys.has(key)}
            isFocused={activeEvidenceKey === key}
            isApproved={isApproved}
            isViewingHistoricalDraft={isViewingHistoricalDraft}
            canUseWorkflowActions={canUseWorkflowActions}
            loading={loading}
            onToggleEvidenceExclusion={onToggleEvidenceExclusion}
            registerCardRef={registerEvidenceCardRef}
          />
        );
      })}
    </article>
  );
}
