import { describe, expect, it } from "vitest";

import {
  buildCitationView,
  buildTimelineText,
  evidenceKey,
  nodeProgressLabel,
  statusLabel,
  tokenizeNumberedCitations,
  workflowSummary,
} from "@/lib/workflow";
import { buildEvidenceItem, buildSession } from "@/test/factories/workflow";

describe("workflow helpers", () => {
  it("maps workflow status labels and summary text", () => {
    expect(statusLabel("awaiting_finalization")).toBe("Finalization In Progress");
    expect(workflowSummary("approved")).toBe("Workflow: Approved (final)");
    expect(workflowSummary(null)).toBe("Workflow: Not started");
  });

  it("returns node progress labels with review and fallback states", () => {
    expect(nodeProgressLabel(null)).toBe("Initializing workflow...");
    expect(
      nodeProgressLabel(
        buildSession({
          current_node: "human_review",
          status: "awaiting_review",
        }),
      ),
    ).toBe("Draft ready for review.");
    expect(
      nodeProgressLabel(
        buildSession({
          current_node: "mystery_node",
          status: "approved",
        }),
      ),
    ).toBe("Final answer approved.");
  });

  it("builds stable evidence keys", () => {
    expect(evidenceKey(buildEvidenceItem({ chunk_id: "chunk-99" }))).toBe("chunk-99");
    expect(
      evidenceKey(
        buildEvidenceItem({
          chunk_id: "",
          document_filename: "Board-Memo.md",
          chunk_index: 5,
        }),
      ),
    ).toBe("board-memo.md::5");
  });

  it("normalizes citation text and tracks citation maps", () => {
    const first = buildEvidenceItem({
      chunk_id: "chunk-1",
      document_filename: "source-a.md",
      chunk_index: 1,
    });
    const second = buildEvidenceItem({
      chunk_id: "chunk-2",
      document_filename: "source-b.md",
      chunk_index: 2,
    });

    const view = buildCitationView(
      "Use [source-b.md#chunk-2], then [1], and [source-b.md#chunk-2] again. Ignore [99].",
      [first, second],
    );

    expect(view.answerText).toBe("Use [1], then [2], and [1] again. Ignore [99].");
    expect(view.citedEvidenceKeys).toEqual(new Set(["chunk-1", "chunk-2"]));
    expect(view.citationByEvidenceKey.get("chunk-2")).toBe(1);
    expect(view.citationByEvidenceKey.get("chunk-1")).toBe(2);
    expect(view.citationKeyByNumber.get(1)).toBe("chunk-2");
  });

  it("tokenizes numbered citations and timeline text", () => {
    const tokens = tokenizeNumberedCitations("Line one [1], line two [2].");

    expect(tokens).toEqual([
      { kind: "text", value: "Line one " },
      { kind: "citation", value: 1, label: "[1]" },
      { kind: "text", value: ", line two " },
      { kind: "citation", value: 2, label: "[2]" },
      { kind: "text", value: "." },
    ]);

    expect(buildTimelineText(buildSession({ status: "revision_requested" }))).toBe(
      "Revision requested. Submit feedback to continue.",
    );
  });
});
