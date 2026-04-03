import { type Session } from "@/lib/api";
import { statusLabel } from "@/lib/workflow";

type StatusBadgeProps = {
  status: Session["status"] | null;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className="status-chip">{status ? statusLabel(status) : "Idle"}</span>;
}
