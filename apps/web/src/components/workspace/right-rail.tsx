import { type UseWorkflowResult } from "@/hooks/use-workflow";
import { type ReviewRailTab, type ReviewWorkspaceModel } from "@/lib/review-models";

import { durationLabel, stageStatusLabel } from "@/components/workspace/ui-utils";

import styles from "./right-rail.module.css";

type ReviewV2RightRailProps = {
  workflow: UseWorkflowResult;
  model: ReviewWorkspaceModel;
  rightTab: ReviewRailTab;
  activeEvidenceKey: string | null;
  evidenceHeaderText: string;
  canUseWorkflowActions: boolean;
  onChangeTab: (tab: ReviewRailTab) => void;
  onSetActiveEvidenceKey: (key: string) => void;
  onSetActiveCitationNumber: (value: number | null) => void;
  onJumpToCitation: (evidenceKey: string, citationNumber: number | null) => void;
  onToggleEvidenceExclusion: (key: string) => void;
  registerEvidenceRef: (key: string, node: HTMLDivElement | null) => void;
};

export function ReviewV2RightRail({
  workflow,
  model,
  rightTab,
  activeEvidenceKey,
  evidenceHeaderText,
  canUseWorkflowActions,
  onChangeTab,
  onSetActiveEvidenceKey,
  onSetActiveCitationNumber,
  onJumpToCitation,
  onToggleEvidenceExclusion,
  registerEvidenceRef,
}: ReviewV2RightRailProps) {
  const evidenceCount = model.evidence.length;
  const gapsCount = model.gaps.length;

  function evidenceStatusClassName(item: (typeof model.evidence)[number]): string {
    if (item.isExcluded) return styles.evidenceExcluded;
    if (item.usedInDraft) return styles.evidenceUsed;
    return styles.evidenceUnused;
  }

  function stageStatusClassName(status: (typeof model.runStages)[number]["status"]): string {
    switch (status) {
      case "done":
        return styles.stageStatusDone;
      case "running":
        return styles.stageStatusRunning;
      case "warning":
        return styles.stageStatusWarning;
      case "failed":
        return styles.stageStatusFailed;
      default:
        return styles.stageStatusIdle;
    }
  }

  return (
    <aside className={styles.rightRail}>
      <div className={styles.railTabs}>
        <button
          type="button"
          className={rightTab === "evidence" ? styles.railTabActive : styles.railTab}
          onClick={() => onChangeTab("evidence")}
        >
          Evidence{evidenceCount ? ` (${evidenceCount})` : ""}
        </button>
        <button
          type="button"
          className={rightTab === "gaps" ? styles.railTabActive : styles.railTab}
          onClick={() => onChangeTab("gaps")}
        >
          Gaps{gapsCount ? ` (${gapsCount})` : ""}
        </button>
        <button
          type="button"
          className={rightTab === "activity" ? styles.railTabActive : styles.railTab}
          onClick={() => onChangeTab("activity")}
        >
          Activity
        </button>
      </div>

      {rightTab === "evidence" ? (
        <section className={styles.railSection}>
          <h3>Evidence</h3>
          <p className={styles.inlineHint}>{evidenceHeaderText}</p>

          {!model.evidence.length ? (
            <p className={styles.inlineHint}>No evidence available yet.</p>
          ) : null}

          {model.evidence.map((item) => {
            const isActive = activeEvidenceKey === item.key;
            return (
              <div
                key={item.key}
                ref={(node) => registerEvidenceRef(item.key, node)}
                className={`${styles.evidenceCard} ${evidenceStatusClassName(item)}${
                  isActive ? ` ${styles.evidenceCardActive}` : ""
                }`}
              >
                <div className={styles.evidenceHeader}>
                  <p>{item.sourceTitle}</p>
                  <span>{item.citationNumber ? `[${item.citationNumber}]` : item.status}</span>
                </div>

                <p className={styles.evidenceExcerpt}>{item.excerpt}</p>

                <div className={styles.evidenceMetaRow}>
                  <span>Chunk {item.chunkIndex}</span>
                  <span>{item.matchReason}</span>
                </div>

                <div className={styles.evidenceActions}>
                  <button
                    type="button"
                    className={styles.ghostButton}
                    onClick={() => {
                      onSetActiveEvidenceKey(item.key);
                      onSetActiveCitationNumber(item.citationNumber);
                      onJumpToCitation(item.key, item.citationNumber);
                    }}
                    disabled={!item.citationNumber}
                  >
                    Focus citation
                  </button>
                  <button
                    type="button"
                    className={styles.ghostButton}
                    onClick={() => onToggleEvidenceExclusion(item.key)}
                    disabled={!canUseWorkflowActions || workflow.loading}
                  >
                    {item.isExcluded ? "Include" : "Exclude"}
                  </button>
                </div>
              </div>
            );
          })}
        </section>
      ) : null}

      {rightTab === "gaps" ? (
        <section className={styles.railSection}>
          <h3>Gaps</h3>
          <p className={styles.inlineHint}>Items that still need review.</p>

          {!model.gaps.length ? <p className={styles.inlineHint}>No open gaps.</p> : null}

          {model.gaps.map((gap) => (
            <div key={gap.id} className={styles.gapCard}>
              <div className={styles.gapHeaderRow}>
                <strong>{gap.title}</strong>
                <span>{gap.severity === "warning" ? "Warning" : "Info"}</span>
              </div>
              <p>{gap.detail}</p>
            </div>
          ))}

          {workflow.requiresGapAcknowledgement ? (
            <label className={styles.gapAcknowledgeRow}>
              <input
                type="checkbox"
                checked={workflow.reviewedEvidenceGaps}
                onChange={(event) => workflow.setReviewedEvidenceGaps(event.target.checked)}
                disabled={workflow.isApproved}
              />
              I reviewed remaining gaps.
            </label>
          ) : null}
        </section>
      ) : null}

      {rightTab === "activity" ? (
        <section className={styles.railSection}>
          <h3>Activity</h3>
          <p className={styles.inlineHint}>Processing timeline for this draft.</p>

          <div className={styles.stageTimeline}>
            {model.runStages.map((stage) => (
              <div key={stage.id} className={`${styles.stageRow} ${stageStatusClassName(stage.status)}`}>
                <span className={styles.stageDot} />
                <div>
                  <div className={styles.stageHeaderRow}>
                    <p>{stage.label}</p>
                    <span className={styles.stageState}>{stageStatusLabel(stage.status)}</span>
                  </div>
                  <p className={styles.stageMeta}>Duration {durationLabel(stage.durationMs)}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </aside>
  );
}
