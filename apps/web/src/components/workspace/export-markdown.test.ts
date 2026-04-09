import { describe, expect, it } from "vitest";

import { buildExportFilename, buildExportMarkdown } from "@/components/workspace/export-markdown";
import type { EvidenceItem, ResponseDocument } from "@/lib/api";

function evidence(overrides: Partial<EvidenceItem>): EvidenceItem {
  return {
    chunk_id: "chunk-1",
    document_id: "doc-1",
    document_title: "Evidence",
    document_filename: "evidence.md",
    chunk_index: 1,
    text: "Evidence text",
    score: 0.9,
    retrieval_method: "semantic",
    metadata: {},
    ...overrides,
  };
}

function buildDocument(): ResponseDocument {
  return {
    id: "doc-1",
    title: "ACME / RFP Response 2026",
    source_filename: "sample-questions.md",
    status: "draft_ready",
    created_at: "2026-04-08T00:00:00Z",
    updated_at: "2026-04-08T00:00:00Z",
    questions: [
      {
        id: "q1",
        order_index: 0,
        extracted_text: "Question One",
        normalized_title: "question-one",
      },
      {
        id: "q2",
        order_index: 1,
        extracted_text: "Question Two",
        normalized_title: "question-two",
      },
    ],
    versions: [
      {
        id: "v1",
        version_number: 1,
        label: "Version 1",
        created_by: "tester",
        parent_version_id: null,
        is_final: true,
        created_at: "2026-04-08T00:00:00Z",
      },
    ],
    selected_version: {
      id: "v1",
      version_number: 1,
      label: "Version 1",
      created_by: "tester",
      parent_version_id: null,
      is_final: true,
      created_at: "2026-04-08T00:00:00Z",
      sections: [
        {
          id: "s1",
          question_id: "q1",
          order_index: 0,
          content_markdown: "First answer [1] and [2].",
          confidence_score: null,
          coverage_score: null,
          evidence_refs: [
            evidence({ chunk_id: "chunk-1", chunk_index: 2, document_filename: "q1-source-a.md", score: 0.91 }),
            evidence({ chunk_id: "chunk-2", chunk_index: 7, document_filename: "q1-source-b.md", score: 0.84 }),
          ],
        },
        {
          id: "s2",
          question_id: "q2",
          order_index: 1,
          content_markdown: "Second answer with targeted evidence [2].",
          confidence_score: null,
          coverage_score: null,
          evidence_refs: [
            evidence({ chunk_id: "chunk-3", chunk_index: 1, document_filename: "q2-unused.md" }),
            evidence({ chunk_id: "chunk-4", chunk_index: 4, document_filename: "q2-used.md", score: 0.77 }),
          ],
        },
      ],
    },
  };
}

describe("buildExportFilename", () => {
  it("slugifies the title and appends version number", () => {
    const fileName = buildExportFilename(buildDocument(), 7);
    expect(fileName).toBe("acme-rfp-response-2026-v7.md");
  });
});

describe("buildExportMarkdown", () => {
  it("includes per-question reference blocks aligned to citations", () => {
    const document = buildDocument();
    const markdown = buildExportMarkdown(document, document.selected_version!);

    expect(markdown).toContain("## Question 1: Question One");
    expect(markdown).toContain("## Question 2: Question Two");
    expect(markdown).toContain("### References");
    expect(markdown).toContain("[1] q1-source-a.md (chunk 2, semantic, score 0.91)");
    expect(markdown).toContain("[2] q1-source-b.md (chunk 7, semantic, score 0.84)");
    expect(markdown).toContain("[2] q2-used.md (chunk 4, semantic, score 0.77)");
    expect(markdown).not.toContain("q2-unused.md");
    expect(markdown).toMatch(/\[2\] q1-source-b\.md[^\n]*\n\n## Question 2: Question Two/);
    expect(markdown).toMatch(/- Exported: .+/);
  });
});
