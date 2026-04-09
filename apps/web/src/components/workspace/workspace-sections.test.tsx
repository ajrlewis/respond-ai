import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  ActivityPanel,
  AIComposer,
  DocumentMetaPanel,
  EditorSurface,
  GeneratingDraftPreview,
  ProcessingStatusStrip,
  StageCard,
  VersionRow,
} from "@/components/workspace/workspace-sections";
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

  it("hides example action and source filename when workspace flags disable them", () => {
    render(
      <DocumentMetaPanel
        document={buildDocument()}
        title="Submission Workspace"
        subtitle="Upload a questionnaire or start from example questions."
        loading={false}
        showExampleQuestions={false}
        showSourceFilename={false}
        onUpload={vi.fn()}
        onUseExamples={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Use example questions" })).not.toBeInTheDocument();
    expect(screen.getByText("3 questions")).toBeInTheDocument();
    expect(screen.queryByText(/Source:/)).not.toBeInTheDocument();
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

    expect(screen.getByRole("button", { name: "Sources (1)" })).toBeInTheDocument();
    expect(screen.queryByText(/Prior RFP Answers/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sources (1)" }));

    expect(screen.getByRole("button", { name: "Hide sources" })).toBeInTheDocument();
    expect(screen.getByText(/\[1\]/)).toBeInTheDocument();
    expect(screen.getByText(/High relevance/)).toBeInTheDocument();
    expect(screen.getByText(/Prior RFP Answers/)).toBeInTheDocument();
  });
});

describe("ProcessingStatusStrip", () => {
  it("shows active stage as a single scoped line while processing", () => {
    render(
      <ProcessingStatusStrip
        title="Applying revision"
        isRunning
        scopeLabel="Question 1 of 1"
        stages={[
          { label: "Analyze revision request", status: "done" },
          { label: "Revise draft text", status: "running" },
          { label: "Prepare editable suggestions", status: "idle" },
        ]}
      />,
    );

    expect(screen.getByText("Applying revision")).toBeInTheDocument();
    expect(screen.getByText("Question 1 of 1: Revise draft text")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
  });
});

describe("StageCard", () => {
  it("does not render a default stage label before the first stage update", () => {
    render(
      <StageCard
        title="Generating draft"
        scopeLabel="Question 1 of 3"
        stages={[
          { label: "Plan approach", status: "idle" },
          { label: "Retrieve supporting material", status: "idle" },
          { label: "Rank evidence", status: "idle" },
        ]}
      />,
    );

    expect(screen.queryByText("Question 1 of 3: Plan approach")).not.toBeInTheDocument();
    expect(screen.queryByText("Plan approach")).not.toBeInTheDocument();
  });

  it("shows running stage as a single scoped line", () => {
    render(
      <StageCard
        title="Generating draft"
        scopeLabel="Question 1 of 3"
        stages={[
          { label: "Retrieve supporting material", status: "done" },
          { label: "Rank evidence", status: "done" },
          { label: "Draft response sections", status: "running" },
        ]}
      />,
    );

    expect(screen.getByText("Question 1 of 3: Draft response sections")).toBeInTheDocument();
  });

  it("keeps status and scoped stage labels visible for varied text lengths", () => {
    render(
      <StageCard
        title="Generating draft"
        scopeLabel="Question 2 of 3"
        stages={[
          { label: "Plan approach", status: "running" },
        ]}
      />,
    );

    expect(screen.getByText("Generating draft")).toBeInTheDocument();
    expect(screen.getByText("Question 2 of 3: Plan approach")).toBeInTheDocument();
  });

  it("shows completion state when all stages are done", () => {
    const { container } = render(
      <StageCard
        title="Generating draft"
        stages={[
          { label: "Retrieve supporting material", status: "done" },
          { label: "Rank evidence", status: "done" },
        ]}
      />,
    );

    expect(screen.getByText("Processing complete")).toBeInTheDocument();
    const indicator = container.querySelector('[aria-hidden="true"]');
    expect(indicator).toBeTruthy();
    expect(indicator?.className).toMatch(/processingDoneDot/);
    expect(indicator?.className).not.toMatch(/runSpinner/);
  });
});

describe("AIComposer", () => {
  it("supports scoped revision targeting", async () => {
    const user = userEvent.setup();
    const onScopeChange = vi.fn();
    const onQuestionChange = vi.fn();

    render(
      <AIComposer
        instruction=""
        askingAi={false}
        loading={false}
        scope="selected_question"
        questions={[
          { id: "q1", label: "Question 1" },
          { id: "q2", label: "Question 2" },
        ]}
        selectedQuestionId="q1"
        onInstructionChange={vi.fn()}
        onScopeChange={onScopeChange}
        onQuestionChange={onQuestionChange}
        onApply={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Scope"), "whole_document");
    expect(onScopeChange).toHaveBeenCalledWith("whole_document");

    await user.selectOptions(screen.getByLabelText("Question"), "q2");
    expect(onQuestionChange).toHaveBeenCalledWith("q2");
  });

  it("applies revision wording and scope flags from workspace config", () => {
    render(
      <AIComposer
        instruction=""
        askingAi={false}
        loading={false}
        scope="selected_question"
        allowQuestionScope={false}
        allowWholeDocumentScope
        helperText="Describe specific edits and keep requests aligned to available evidence."
        submitButtonLabel="Request Revision"
        questions={[
          { id: "q1", label: "Question 1" },
        ]}
        selectedQuestionId="q1"
        onInstructionChange={vi.fn()}
        onScopeChange={vi.fn()}
        onQuestionChange={vi.fn()}
        onApply={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText("Scope")).not.toBeInTheDocument();
    expect(screen.getByText("Describe specific edits and keep requests aligned to available evidence.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request Revision" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
  });
});

describe("GeneratingDraftPreview", () => {
  it("shows streamed answer content for completed questions", () => {
    const document = buildDocument();
    render(
      <GeneratingDraftPreview
        questions={document.questions.slice(0, 2)}
        sectionsByQuestionId={{ q1: "Generated answer 1", q2: "" }}
        evidenceByQuestionId={{}}
      />,
    );

    expect(screen.getByLabelText("Draft answer for question 1")).toHaveValue("Generated answer 1");
    expect(screen.getByLabelText("Draft answer for question 2")).toHaveValue("");
  });

  it("renders per-question supporting sources toggle while generating", async () => {
    const user = userEvent.setup();
    const document = buildDocument();
    render(
      <GeneratingDraftPreview
        questions={document.questions.slice(0, 1)}
        sectionsByQuestionId={{ q1: "Generated answer 1" }}
        evidenceByQuestionId={{
          q1: [
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
        }}
      />,
    );

    expect(screen.getByRole("button", { name: "Sources (1)" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sources (1)" }));
    expect(screen.getByRole("button", { name: "Hide sources" })).toBeInTheDocument();
    expect(screen.getByText(/Prior RFP Answers/)).toBeInTheDocument();
  });
});

describe("ActivityPanel", () => {
  it("renders stage timeline for the latest processing run", () => {
    render(
      <ActivityPanel
        title="Generating draft"
        subtitle="Preparing a document-level response across all sections."
        isRunning={false}
        hasRunHistory
        stages={[
          { label: "Retrieve supporting material", status: "done" },
          { label: "Rank evidence", status: "done" },
          { label: "Draft response sections", status: "done" },
          { label: "Review citations", status: "done" },
        ]}
      />,
    );

    expect(screen.getByText("Activity")).toBeInTheDocument();
    expect(screen.getByText("Generating draft")).toBeInTheDocument();
    expect(screen.getByText("Retrieve supporting material")).toBeInTheDocument();
    expect(screen.getAllByText("Done").length).toBeGreaterThan(0);
  });
});
