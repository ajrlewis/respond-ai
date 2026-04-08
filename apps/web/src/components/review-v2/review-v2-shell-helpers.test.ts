import { describe, expect, it } from "vitest";

import {
  markAllStagesDone,
  syncSectionContentAndEvidence,
  updateStagesFromServer,
} from "@/components/review-v2/review-v2-shell-helpers";
import type { EvidenceItem } from "@/lib/api";

function evidenceItem(id: string): EvidenceItem {
  return {
    chunk_id: id,
    document_id: `doc-${id}`,
    document_title: `Source ${id}`,
    document_filename: `${id}.md`,
    chunk_index: 0,
    text: `Evidence ${id}`,
    score: 0.8,
    retrieval_method: "semantic",
    metadata: {},
  };
}

describe("syncSectionContentAndEvidence", () => {
  it("keeps only cited evidence and preserves numbering when already contiguous", () => {
    const synced = syncSectionContentAndEvidence(
      "A concise statement [1].",
      [evidenceItem("a"), evidenceItem("b"), evidenceItem("c")],
    );

    expect(synced.contentMarkdown).toBe("A concise statement [1].");
    expect(synced.evidenceRefs.map((item) => item.chunk_id)).toEqual(["a"]);
  });

  it("renumbers sparse citations and remaps evidence order", () => {
    const synced = syncSectionContentAndEvidence(
      "Portfolio evidence [2] with secondary support [4].",
      [evidenceItem("a"), evidenceItem("b"), evidenceItem("c"), evidenceItem("d")],
    );

    expect(synced.contentMarkdown).toBe("Portfolio evidence [1] with secondary support [2].");
    expect(synced.evidenceRefs.map((item) => item.chunk_id)).toEqual(["b", "d"]);
  });

  it("drops all evidence refs when no numeric citations remain", () => {
    const synced = syncSectionContentAndEvidence(
      "Updated answer without explicit citations.",
      [evidenceItem("a"), evidenceItem("b")],
    );

    expect(synced.contentMarkdown).toBe("Updated answer without explicit citations.");
    expect(synced.evidenceRefs).toEqual([]);
  });
});

describe("updateStagesFromServer", () => {
  it("advances running stage and marks prior stages done", () => {
    const next = updateStagesFromServer(
      [
        { label: "Retrieve supporting material", status: "running" },
        { label: "Rank evidence", status: "idle" },
        { label: "Draft response sections", status: "idle" },
      ],
      "Rank evidence",
      "running",
    );

    expect(next).toEqual([
      { label: "Retrieve supporting material", status: "done" },
      { label: "Rank evidence", status: "running" },
      { label: "Draft response sections", status: "idle" },
    ]);
  });

  it("appends unknown server stage labels in order", () => {
    const next = updateStagesFromServer(
      [{ label: "Analyze revision request", status: "running" }],
      "Prepare editable suggestions",
      "running",
    );

    expect(next).toEqual([
      { label: "Analyze revision request", status: "done" },
      { label: "Prepare editable suggestions", status: "running" },
    ]);
  });
});

describe("markAllStagesDone", () => {
  it("marks every stage as done", () => {
    const next = markAllStagesDone([
      { label: "Retrieve supporting material", status: "running" },
      { label: "Rank evidence", status: "idle" },
    ]);

    expect(next).toEqual([
      { label: "Retrieve supporting material", status: "done" },
      { label: "Rank evidence", status: "done" },
    ]);
  });
});
