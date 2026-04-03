import { type ReactNode } from "react";

type DisclosurePanelProps = {
  title: string;
  summary: string;
  expanded: boolean;
  onToggle: () => void;
  showLabel: string;
  hideLabel: string;
  tone?: "default" | "caution";
  children: ReactNode;
};

export function DisclosurePanel({
  title,
  summary,
  expanded,
  onToggle,
  showLabel,
  hideLabel,
  tone = "default",
  children,
}: DisclosurePanelProps) {
  return (
    <section className={`disclosure-card${tone === "caution" ? " disclosure-card-caution" : ""}`}>
      <div className="disclosure-header">
        <div>
          <h3>{title}</h3>
          <p className="disclosure-summary-line">{summary}</p>
        </div>
        <button type="button" className="secondary disclosure-trigger" onClick={onToggle} aria-expanded={expanded}>
          {expanded ? hideLabel : showLabel}
        </button>
      </div>
      <div className={`disclosure-panel${expanded ? " open" : ""}`}>
        <div className="disclosure-panel-inner">{children}</div>
      </div>
    </section>
  );
}
