import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ActionBar } from "@/components/workflow/action-bar";

describe("ActionBar", () => {
  it("does not render when workflow actions are unavailable", () => {
    const { container } = render(
      <ActionBar
        canUseWorkflowActions={false}
        canApprove={false}
        approveWarning={false}
        isGapAcknowledged={false}
        confidenceScore={null}
        approveButtonLabel="Approve"
        reviewMode="none"
        loading={false}
        onApprove={vi.fn()}
        onToggleRevision={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders warning state and fires action callbacks", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    const onToggleRevision = vi.fn();

    render(
      <ActionBar
        canUseWorkflowActions
        canApprove
        approveWarning
        isGapAcknowledged
        confidenceScore={0.63}
        approveButtonLabel="Approve (Low Confidence)"
        reviewMode="none"
        loading={false}
        onApprove={onApprove}
        onToggleRevision={onToggleRevision}
      />,
    );

    const approveButton = screen.getByRole("button", { name: "Approve (Low Confidence)" });
    expect(approveButton).toHaveClass("warning");
    expect(approveButton).toHaveAttribute("title", "Low confidence (0.63). Approval requires confirmation.");

    await user.click(approveButton);
    await user.click(screen.getByRole("button", { name: "Revise" }));

    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onToggleRevision).toHaveBeenCalledTimes(1);
  });
});
