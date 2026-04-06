import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SourceCard } from "@/components/workflow/source-card";
import { buildEvidenceItem } from "@/test/factories/workflow";

describe("SourceCard", () => {
  it("renders citation details and supports exclusion toggling", async () => {
    const user = userEvent.setup();
    const onToggleEvidenceExclusion = vi.fn();

    render(
      <SourceCard
        item={buildEvidenceItem({ document_filename: "memo.md", chunk_index: 3, score: 0.734, retrieval_method: "semantic" })}
        sourceKey="chunk-3"
        citationNumber={2}
        isCitedChunk
        isExcluded={false}
        isFocused={false}
        isApproved={false}
        isViewingHistoricalDraft={false}
        canUseWorkflowActions
        loading={false}
        onToggleEvidenceExclusion={onToggleEvidenceExclusion}
        registerCardRef={vi.fn()}
      />,
    );

    expect(screen.getByText("[2]")).toBeInTheDocument();
    expect(screen.getByText("memo.md")).toBeInTheDocument();
    expect(screen.getByText(/Chunk 3/i)).toBeInTheDocument();
    expect(screen.getByText(/Semantic match/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exclude in next revision" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Exclude in next revision" }));

    expect(onToggleEvidenceExclusion).toHaveBeenCalledWith("chunk-3");
  });

  it("shows excluded state and hides controls when actions are unavailable", () => {
    const { rerender } = render(
      <SourceCard
        item={buildEvidenceItem({ score: 0.5, retrieval_method: "keyword" })}
        sourceKey="chunk-1"
        citationNumber={undefined}
        isCitedChunk={false}
        isExcluded
        isFocused={false}
        isApproved={false}
        isViewingHistoricalDraft={false}
        canUseWorkflowActions
        loading
        onToggleEvidenceExclusion={vi.fn()}
        registerCardRef={vi.fn()}
      />,
    );

    expect(screen.getByText("Excluded from revision")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Include in next revision" })).toBeDisabled();

    rerender(
      <SourceCard
        item={buildEvidenceItem()}
        sourceKey="chunk-1"
        citationNumber={undefined}
        isCitedChunk={false}
        isExcluded={false}
        isFocused={false}
        isApproved={false}
        isViewingHistoricalDraft={false}
        canUseWorkflowActions={false}
        loading={false}
        onToggleEvidenceExclusion={vi.fn()}
        registerCardRef={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: /revision/i })).not.toBeInTheDocument();
  });
});
