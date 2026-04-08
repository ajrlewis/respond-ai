import { describe, expect, it } from "vitest";

import { buildReviewWorkspaceModel, type WorkflowActivityEvent } from "@/lib/review-models";
import { buildAnswerVersion, buildConfidence, buildEvidenceItem, buildSession } from "@/test/factories/workflow";

function buildActivityEvent(overrides: Partial<WorkflowActivityEvent> = {}): WorkflowActivityEvent {
  return {
    id: "event-1",
    timestamp: "2026-01-01T00:00:00.000Z",
    reason: "update",
    node: "ask",
    status: "draft",
    error: null,
    ...overrides,
  };
}

describe("buildReviewWorkspaceModel", () => {
  it("maps citations, evidence status, and paragraph grounding states", () => {
    const evidenceOne = buildEvidenceItem({ chunk_id: "chunk-1", score: 0.92 });
    const evidenceTwo = buildEvidenceItem({ chunk_id: "chunk-2", chunk_index: 2, score: 0.61, text: "Lower-confidence excerpt" });

    const answerText = "Grounded paragraph [1]\n\nWeak paragraph [2]\n\nUnverified paragraph.";
    const session = buildSession({
      evidence: [evidenceOne, evidenceTwo],
      draft_answer: answerText,
      status: "awaiting_review",
      current_node: "human_review",
    });

    const model = buildReviewWorkspaceModel({
      questionText: session.question_text,
      session,
      answerText,
      selectedVersionLabel: "Draft 2",
      selectedVersionStatus: "Awaiting Review",
      isReadOnly: false,
      citationKeyByNumber: new Map([
        [1, "chunk-1"],
        [2, "chunk-2"],
      ]),
      citationByEvidenceKey: new Map([
        ["chunk-1", 1],
        ["chunk-2", 2],
      ]),
      citedEvidenceKeys: new Set(["chunk-1", "chunk-2"]),
      excludedEvidenceKeys: new Set(["chunk-2"]),
      drafts: [buildAnswerVersion()],
      compareSegments: [],
      isCompareMode: false,
      activityEvents: [buildActivityEvent()],
    });

    expect(model.summary.citationCount).toBe(2);
    expect(model.summary.evidenceCoverage).toEqual({ cited: 2, total: 2, percentage: 100 });
    expect(model.evidence.find((item) => item.key === "chunk-2")?.status).toBe("excluded");
    expect(model.draft.paragraphs.map((paragraph) => paragraph.state)).toEqual([
      "grounded",
      "weak_evidence",
      "unverified",
    ]);
  });

  it("builds warning status for review confidence when gaps or low confidence exist", () => {
    const session = buildSession({
      status: "awaiting_review",
      current_node: "human_review",
      confidence: buildConfidence({ score: 0.62, evidence_gaps: ["Missing compliance evidence"] }),
      evidence_gap_count: 1,
      requires_gap_acknowledgement: true,
    });

    const model = buildReviewWorkspaceModel({
      questionText: session.question_text,
      session,
      answerText: "Draft answer [1]",
      selectedVersionLabel: "Draft 1",
      selectedVersionStatus: "Awaiting Review",
      isReadOnly: false,
      citationKeyByNumber: new Map([[1, "chunk-1"]]),
      citationByEvidenceKey: new Map([["chunk-1", 1]]),
      citedEvidenceKeys: new Set(["chunk-1"]),
      excludedEvidenceKeys: new Set(),
      drafts: [buildAnswerVersion()],
      compareSegments: [],
      isCompareMode: false,
      activityEvents: [
        buildActivityEvent({ id: "e1", node: "retrieve_evidence" }),
        buildActivityEvent({ id: "e2", node: "draft_response", timestamp: "2026-01-01T00:00:20.000Z" }),
        buildActivityEvent({ id: "e3", node: "human_review", timestamp: "2026-01-01T00:00:35.000Z" }),
      ],
    });

    const reviewStage = model.runStages.find((stage) => stage.id === "review_confidence");
    expect(reviewStage?.status).toBe("warning");

    const retrieveStage = model.runStages.find((stage) => stage.id === "retrieve_context");
    expect(retrieveStage?.status).toBe("done");
  });

  it("marks all run stages as done for approved sessions and sorts revisions newest first", () => {
    const session = buildSession({ status: "approved", current_node: "finalize_response", final_answer: "Final text [1]" });
    const draftOne = buildAnswerVersion({ version_id: "draft-1", version_number: 1, label: "Draft 1", is_current: false });
    const draftTwo = buildAnswerVersion({ version_id: "draft-2", version_number: 2, label: "Draft 2", is_current: true, is_approved: true });

    const model = buildReviewWorkspaceModel({
      questionText: session.question_text,
      session,
      answerText: "Final text [1]",
      selectedVersionLabel: "Draft 2",
      selectedVersionStatus: "Approved",
      isReadOnly: false,
      citationKeyByNumber: new Map([[1, "chunk-1"]]),
      citationByEvidenceKey: new Map([["chunk-1", 1]]),
      citedEvidenceKeys: new Set(["chunk-1"]),
      excludedEvidenceKeys: new Set(),
      drafts: [draftOne, draftTwo],
      compareSegments: [],
      isCompareMode: false,
      activityEvents: [buildActivityEvent({ node: "finalize_response" })],
    });

    expect(model.runStages.every((stage) => stage.status === "done")).toBe(true);
    expect(model.revisions.map((revision) => revision.id)).toEqual(["draft-2", "draft-1"]);
  });
});
