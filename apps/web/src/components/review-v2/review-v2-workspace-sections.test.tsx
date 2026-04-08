import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  DocumentMetaPanel,
  EditorSurface,
  VersionRow,
} from "@/components/review-v2/review-v2-workspace-sections";
import type { ResponseDocument } from "@/lib/api";

function buildDocument(): ResponseDocument {
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
        normalized_title: "Question 1",
      },
      {
        id: "q2",
        order_index: 1,
        extracted_text: "Question 2",
        normalized_title: "Question 2",
      },
      {
        id: "q3",
        order_index: 2,
        extracted_text: "Question 3",
        normalized_title: "Question 3",
      },
    ],
    versions: [
      {
        id: "v1",
        version_number: 1,
        label: "Version 1",
        created_by: "tester",
        parent_version_id: null,
        is_final: false,
        created_at: "2026-04-08T00:00:00Z",
      },
      {
        id: "v2",
        version_number: 2,
        label: "Version 2",
        created_by: "tester",
        parent_version_id: "v1",
        is_final: false,
        created_at: "2026-04-08T00:10:00Z",
      },
    ],
    selected_version: null,
  };
}

describe("DocumentMetaPanel", () => {
  it("shows upload actions only before a document is loaded", () => {
    render(
      <DocumentMetaPanel
        document={null}
        title="Submission Workspace"
        subtitle="Upload a questionnaire or start from example questions."
        loading={false}
        onUpload={vi.fn()}
        onUseExamples={vi.fn()}
      />,
    );

    expect(screen.getByText("Submission Workspace")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload document" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use example questions" })).toBeInTheDocument();
  });

  it("shows compact document metadata after load", () => {
    render(
      <DocumentMetaPanel
        document={buildDocument()}
        title="Submission Workspace"
        subtitle="Upload a questionnaire or start from example questions."
        loading={false}
        onUpload={vi.fn()}
        onUseExamples={vi.fn()}
      />,
    );

    expect(screen.getByText("Sample Response Draft")).toBeInTheDocument();
    expect(screen.getByText("3 questions · Source: sample-questions.md")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload document" })).not.toBeInTheDocument();
  });
});

describe("VersionRow", () => {
  it("shows delete affordance only for the active version and supports actions", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    const document = buildDocument();

    render(
      <VersionRow
        versions={document.versions}
        selectedVersionId="v2"
        loading={false}
        onSelect={onSelect}
        onDelete={onDelete}
      />,
    );

    expect(screen.getByLabelText("Delete Version 2")).toBeInTheDocument();
    expect(screen.queryByLabelText("Delete Version 1")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Version 1" }));
    expect(onSelect).toHaveBeenCalledWith("v1");

    await user.click(screen.getByLabelText("Delete Version 2"));
    expect(onDelete).toHaveBeenCalledWith(document.versions[1]);
  });
});

describe("EditorSurface", () => {
  it("keeps supporting sources collapsed until user expands", async () => {
    const user = userEvent.setup();
    const document = buildDocument();
    const onSectionChange = vi.fn();

    render(
      <EditorSurface
        questions={document.questions.slice(0, 1)}
        sectionsByQuestionId={{
          q1: {
            id: "s1",
            question_id: "q1",
            order_index: 0,
            content_markdown: "Answer",
            confidence_score: 0.8,
            coverage_score: 0.7,
            evidence_refs: [
              {
                chunk_id: "chunk-1",
                document_id: "doc-1",
                document_title: "Prior RFP Answers",
                document_filename: "prior_rfp_answers.md",
                chunk_index: 2,
                text: "We have extensive experience investing in renewable energy infrastructure.",
                score: 0.91,
                retrieval_method: "semantic",
                metadata: {},
              },
            ],
          },
        }}
        editableSections={{ q1: "Current draft answer" }}
        hasUnsavedChanges={false}
        globalNotice={null}
        onSectionChange={onSectionChange}
      />,
    );

    expect(screen.getByRole("button", { name: "Show supporting sources (1)" })).toBeInTheDocument();
    expect(screen.queryByText(/Prior RFP Answers/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show supporting sources (1)" }));

    expect(screen.getByRole("button", { name: "Hide supporting sources" })).toBeInTheDocument();
    expect(screen.getByText(/\[1\]/)).toBeInTheDocument();
    expect(screen.getByText(/High relevance/)).toBeInTheDocument();
    expect(screen.getByText(/Prior RFP Answers/)).toBeInTheDocument();
  });
});
