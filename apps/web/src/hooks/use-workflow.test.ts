import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { useWorkflow } from "@/hooks/use-workflow";
import { buildConfidence, buildSession } from "@/test/factories/workflow";
import { getLatestMockEventSource } from "@/test/mocks/event-source";
import { server } from "@/test/msw/server";

const API_BASE_URL = "http://localhost:8000";

describe("useWorkflow", () => {
  it("submits a draft request and settles after workflow stream update", async () => {
    const askedSession = buildSession({
      id: "session-ask-1",
      status: "draft",
      current_node: "draft_response",
      updated_at: "2026-01-01T00:00:00.000Z",
    });
    const settledSession = buildSession({
      id: "session-ask-1",
      status: "awaiting_review",
      current_node: "human_review",
      updated_at: "2026-01-01T00:01:00.000Z",
    });

    server.use(
      http.post(`${API_BASE_URL}/api/questions/ask`, () => HttpResponse.json({ session: askedSession })),
    );

    const { result } = renderHook(() => useWorkflow("reviewer-1"));

    act(() => {
      result.current.setQuestion("How does your strategy create value over the hold period?");
    });

    await act(async () => {
      await result.current.handleGenerateDraft();
    });

    expect(result.current.session?.id).toBe("session-ask-1");
    expect(result.current.isGeneratingDraft).toBe(true);
    expect(result.current.loading).toBe(true);

    const source = getLatestMockEventSource();
    expect(source).not.toBeNull();

    act(() => {
      source?.emit("workflow_state", {
        reason: "update",
        session: settledSession,
      });
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
      expect(result.current.isGeneratingDraft).toBe(false);
      expect(result.current.generationProgress).toBe("Draft ready for review.");
    });
  });

  it("surfaces API errors for draft generation", async () => {
    server.use(
      http.post(`${API_BASE_URL}/api/questions/ask`, () =>
        HttpResponse.json({ detail: "Question service unavailable" }, { status: 503 }),
      ),
    );

    const { result } = renderHook(() => useWorkflow("reviewer-1"));

    act(() => {
      result.current.setQuestion("Describe recent solar and storage investments in detail.");
    });

    await act(async () => {
      await result.current.handleGenerateDraft();
    });

    await waitFor(() => {
      expect(result.current.error).toBe("Question service unavailable");
      expect(result.current.loading).toBe(false);
      expect(result.current.isGeneratingDraft).toBe(false);
    });
  });

  it("blocks approval until evidence gaps are acknowledged", async () => {
    const gappedSession = buildSession({
      id: "session-gaps",
      confidence: buildConfidence({
        score: 0.93,
        evidence_gaps: ["Missing source validation"],
      }),
      evidence_gap_count: 1,
      requires_gap_acknowledgement: true,
      evidence_gaps_acknowledged: false,
      status: "awaiting_review",
      current_node: "human_review",
    });

    server.use(
      http.post(`${API_BASE_URL}/api/questions/ask`, () => HttpResponse.json({ session: gappedSession })),
    );

    const { result } = renderHook(() => useWorkflow("reviewer-1"));

    act(() => {
      result.current.setQuestion("Explain your ESG risk process with governance evidence.");
    });

    await act(async () => {
      await result.current.handleGenerateDraft();
    });

    act(() => {
      getLatestMockEventSource()?.emit("workflow_state", {
        reason: "update",
        session: gappedSession,
      });
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.handleApprove({ selectedDraft: null, isCompareMode: false });
    });

    expect(result.current.error).toBe("Review and acknowledge evidence gaps before approval.");
    expect(result.current.isReviewSummaryExpanded).toBe(true);
    expect(result.current.isEvidenceGapsExpanded).toBe(true);
  });
});
