import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReviewV2EditingView } from "@/components/workspace/editing-view";
import type { ResponseDocument } from "@/lib/api";

function buildDocument(isFinal: boolean): ResponseDocument {
  return {
    id: "doc-1",
    title: "Sample Response Draft",
    source_filename: "sample-questions.md",
    status: "draft_ready",
    created_at: "2026-04-08T00:00:00Z",
    updated_at: "2026-04-08T00:00:00Z",
    questions: [
      {
        id: "q1",
        order_index: 0,
        extracted_text: "Question 1",
        normalized_title: "question-1",
      },
    ],
    versions: [
      {
        id: "v1",
        version_number: 1,
        label: "Version 1",
        created_by: "tester",
        parent_version_id: null,
        is_final: isFinal,
        created_at: "2026-04-08T00:00:00Z",
      },
    ],
    selected_version: {
      id: "v1",
      version_number: 1,
      label: "Version 1",
      created_by: "tester",
      parent_version_id: null,
      is_final: isFinal,
      created_at: "2026-04-08T00:00:00Z",
      sections: [
        {
          id: "s1",
          question_id: "q1",
          order_index: 0,
          content_markdown: "Answer 1",
          confidence_score: null,
          coverage_score: null,
          evidence_refs: [],
        },
      ],
    },
  };
}

function renderView(isFinal: boolean, onExport = vi.fn()) {
  render(
    <ReviewV2EditingView
      document={buildDocument(isFinal)}
      editableSections={{ q1: "Answer 1" }}
      hasUnsavedChanges={false}
      hasGlobalEvidenceWarning={false}
      isAiComposerOpen={false}
      aiInstruction=""
      revisionScope="selected_question"
      revisionQuestionId="q1"
      isAskingAi={false}
      isSavingVersion={false}
      isApproving={false}
      loading={false}
      isProcessing={false}
      deletingVersionId={null}
      notice={null}
      inspectionPanel={null}
      compareData={null}
      compareLeftVersionId={null}
      compareRightVersionId={null}
      onSwitchVersion={vi.fn()}
      onDeleteVersion={vi.fn()}
      onToggleComposer={vi.fn()}
      onInstructionChange={vi.fn()}
      onRevisionScopeChange={vi.fn()}
      onRevisionQuestionChange={vi.fn()}
      onSubmitRevision={vi.fn()}
      onCancelRevision={vi.fn()}
      onSectionChange={vi.fn()}
      onSectionFocus={vi.fn()}
      onSaveVersion={vi.fn()}
      onExport={onExport}
      onApprove={vi.fn()}
      canSuggestChanges
      allowQuestionScopedRevision
      allowFullDocumentRevision
      revisionSubmitButtonLabel="Apply suggestions"
      revisionHelperText="Help text"
      approveButtonLabel="Approve Version"
      approveHelperText="Approval help"
      onToggleCompare={vi.fn()}
      onCompare={vi.fn()}
      onCompareLeftChange={vi.fn()}
      onCompareRightChange={vi.fn()}
    />,
  );
}

describe("ReviewV2EditingView action buttons", () => {
  it("shows Save draft while version is not approved", () => {
    renderView(false);

    expect(screen.getByRole("button", { name: "Save draft" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export Markdown" })).not.toBeInTheDocument();
  });

  it("replaces Save draft with Export Markdown once approved", async () => {
    const user = userEvent.setup();
    const onExport = vi.fn();
    renderView(true, onExport);

    expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export Markdown" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approved" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Export Markdown" }));
    expect(onExport).toHaveBeenCalledTimes(1);
  });
});
