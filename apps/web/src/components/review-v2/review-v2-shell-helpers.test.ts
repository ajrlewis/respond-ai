import { describe, expect, it } from "vitest";

import { syncSectionContentAndEvidence } from "@/components/review-v2/review-v2-shell-helpers";
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
