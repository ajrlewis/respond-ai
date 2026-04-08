import { ReviewV2RightRail } from "@/components/workspace/right-rail";
import { type UseWorkflowResult } from "@/hooks/use-workflow";
import { type ReviewRailTab, type ReviewWorkspaceModel } from "@/lib/review-models";

import styles from "./shell.module.css";

type ReviewV2AssistDrawerProps = {
  isOpen: boolean;
  rightTab: ReviewRailTab;
  workflow: UseWorkflowResult;
  model: ReviewWorkspaceModel;
  activeEvidenceKey: string | null;
  evidenceHeaderText: string;
  canUseWorkflowActions: boolean;
  onClose: () => void;
  onChangeTab: (tab: ReviewRailTab) => void;
  onSetActiveEvidenceKey: (key: string | null) => void;
  onSetActiveCitationNumber: (value: number | null) => void;
  onJumpToCitation: (evidenceKey: string, citationNumber: number | null) => void;
  onToggleEvidenceExclusion: (key: string) => void;
  registerEvidenceRef: (key: string, node: HTMLDivElement | null) => void;
};

export function ReviewV2AssistDrawer({
  isOpen,
  rightTab,
  workflow,
  model,
  activeEvidenceKey,
  evidenceHeaderText,
  canUseWorkflowActions,
  onClose,
  onChangeTab,
  onSetActiveEvidenceKey,
  onSetActiveCitationNumber,
  onJumpToCitation,
  onToggleEvidenceExclusion,
  registerEvidenceRef,
}: ReviewV2AssistDrawerProps) {
  if (!isOpen) return null;

  const title =
    rightTab === "activity" ? "Activity" : rightTab === "gaps" ? "Gaps" : "Evidence";

  return (
    <>
      <button
        type="button"
        className={styles.drawerBackdrop}
        aria-label="Close details panel"
        onClick={onClose}
      />
      <div className={styles.drawer}>
        <div className={styles.drawerHeader}>
          <h2>{title}</h2>
          <button type="button" className={styles.ghostButton} onClick={onClose}>
            Close
          </button>
        </div>

        <ReviewV2RightRail
          workflow={workflow}
          model={model}
          rightTab={rightTab}
          activeEvidenceKey={activeEvidenceKey}
          evidenceHeaderText={evidenceHeaderText}
          canUseWorkflowActions={canUseWorkflowActions}
          onChangeTab={onChangeTab}
          onSetActiveEvidenceKey={(key) => onSetActiveEvidenceKey(key)}
          onSetActiveCitationNumber={onSetActiveCitationNumber}
          onJumpToCitation={onJumpToCitation}
          onToggleEvidenceExclusion={onToggleEvidenceExclusion}
          registerEvidenceRef={registerEvidenceRef}
        />
      </div>
    </>
  );
}
