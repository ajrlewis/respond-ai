import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RevisionHistory } from "@/components/workflow/revision-history";
import { buildAnswerVersion } from "@/test/factories/workflow";

describe("RevisionHistory", () => {
  it("renders empty-state guidance", () => {
    render(
      <RevisionHistory
        drafts={[]}
        latestSnapshotTimestamp={null}
        selectedDraft={null}
        selectedDraftId={null}
        compareDraftId=""
        compareEnabled={false}
        compareTargetDraft={null}
        compareSegments={[]}
        isViewingHistoricalDraft={false}
        isCompareMode={false}
        expanded
        onToggle={vi.fn()}
        onSelectDraft={vi.fn()}
        onSelectCompareDraft={vi.fn()}
      />,
    );

    expect(screen.getByText("No draft versions yet.")).toBeInTheDocument();
    expect(screen.getByText(/Draft history will appear after the first draft/i)).toBeInTheDocument();
  });

  it("supports draft selection and compare mode messaging", async () => {
    const user = userEvent.setup();
    const onSelectDraft = vi.fn();
    const onSelectCompareDraft = vi.fn();
    const first = buildAnswerVersion({ version_id: "draft-1", version_number: 1, label: "Draft 1", is_current: false });
    const second = buildAnswerVersion({ version_id: "draft-2", version_number: 2, label: "Draft 2", is_current: true });

    render(
      <RevisionHistory
        drafts={[first, second]}
        latestSnapshotTimestamp="2026-01-02T10:00:00.000Z"
        selectedDraft={second}
        selectedDraftId="draft-2"
        compareDraftId="draft-1"
        compareEnabled
        compareTargetDraft={first}
        compareSegments={[{ kind: "added", text: "Updated wording" }]}
        isViewingHistoricalDraft={false}
        isCompareMode
        expanded
        onToggle={vi.fn()}
        onSelectDraft={onSelectDraft}
        onSelectCompareDraft={onSelectCompareDraft}
      />,
    );

    expect(screen.getByText(/2 draft versions/i)).toBeInTheDocument();
    expect(screen.getByText(/Comparison mode is read-only/i)).toBeInTheDocument();
    expect(screen.getByText(/Diff: Draft 1 vs Draft 2/i)).toBeInTheDocument();

    const comboboxes = screen.getAllByRole("combobox");
    await user.selectOptions(comboboxes[0], "draft-1");
    await user.selectOptions(comboboxes[1], "");

    expect(onSelectDraft).toHaveBeenCalledWith("draft-1");
    expect(onSelectCompareDraft).toHaveBeenCalledWith("");
  });
});
