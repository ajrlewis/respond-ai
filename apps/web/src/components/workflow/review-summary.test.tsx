import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReviewSummary } from "@/components/workflow/review-summary";
import { buildConfidence } from "@/test/factories/workflow";

describe("ReviewSummary", () => {
  it("renders summary and optional evaluator metadata", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();

    render(
      <ReviewSummary
        confidenceScore={0.87}
        complianceSummary="Passed"
        evidenceGapCount={2}
        citationCount={3}
        confidenceNotes="Reviewer-facing confidence summary"
        evidenceCount={4}
        confidence={
          buildConfidence({
            score: 0.87,
            retrieval_strategy: "adaptive",
            coverage: "partial",
            recommended_action: "proceed_with_caveats",
            model_notes: "Model found minor caveats",
            retrieval_notes: "Retrieval has one weak source",
          })
        }
        expanded={false}
        onToggle={onToggle}
      />,
    );

    expect(
      screen.getByText("Confidence: 0.87 · Compliance: Passed · 2 evidence gaps · 3 citations"),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 evidence gaps/i)).toBeInTheDocument();
    expect(screen.getByText(/Evidence coverage: 3\/4 cited chunks/i)).toBeInTheDocument();
    expect(screen.getByText(/Retrieval strategy: adaptive/i)).toBeInTheDocument();
    expect(screen.getByText(/Evaluator recommendation:/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "View details" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("uses fallback copy when notes are missing", () => {
    render(
      <ReviewSummary
        confidenceScore={null}
        complianceSummary="Unknown"
        evidenceGapCount={0}
        citationCount={0}
        confidenceNotes={null}
        evidenceCount={0}
        confidence={
          buildConfidence({
            score: null,
            model_notes: "",
            retrieval_notes: "",
            recommended_action: "unknown",
            coverage: "unknown",
            retrieval_strategy: null,
          })
        }
        expanded
        onToggle={vi.fn()}
      />,
    );

    expect(screen.getByText("No confidence notes available.")).toBeInTheDocument();
    expect(screen.getByText(/No model notes provided./i)).toBeInTheDocument();
    expect(screen.getByText(/No retrieval notes provided./i)).toBeInTheDocument();
    expect(screen.queryByText(/Evaluator recommendation/i)).not.toBeInTheDocument();
  });
});
