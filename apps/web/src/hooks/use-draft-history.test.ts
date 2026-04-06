import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { useDraftHistory } from "@/hooks/use-draft-history";
import { type DraftComparison } from "@/lib/api";
import { buildAnswerVersion, buildSession } from "@/test/factories/workflow";
import { server } from "@/test/msw/server";

const API_BASE_URL = "http://localhost:8000";

describe("useDraftHistory", () => {
  it("loads drafts and compare segments from API", async () => {
    const firstDraft = buildAnswerVersion({
      version_id: "draft-1",
      version_number: 1,
      label: "Draft 1",
      is_current: false,
      status: "historical",
    });
    const secondDraft = buildAnswerVersion({
      version_id: "draft-2",
      version_number: 2,
      label: "Draft 2",
      is_current: true,
      status: "draft",
    });

    const comparison: DraftComparison = {
      left: firstDraft,
      right: secondDraft,
      segments: [
        { kind: "same", text: "Base" },
        { kind: "added", text: " with update" },
      ],
    };

    server.use(
      http.get(`${API_BASE_URL}/api/questions/:sessionId/drafts`, () => HttpResponse.json([firstDraft, secondDraft])),
      http.get(`${API_BASE_URL}/api/questions/:sessionId/drafts/compare`, () => HttpResponse.json(comparison)),
    );

    const session = buildSession({ id: "session-123", answer_versions: [firstDraft, secondDraft] });
    const { result } = renderHook(() => useDraftHistory({ session }));

    await waitFor(() => {
      expect(result.current.drafts).toHaveLength(2);
      expect(result.current.currentDraft?.version_id).toBe("draft-2");
      expect(result.current.selectedDraft?.version_id).toBe("draft-2");
    });

    act(() => {
      result.current.setCompareSelection("draft-1");
    });

    await waitFor(() => {
      expect(result.current.isCompareMode).toBe(true);
      expect(result.current.compareSegments).toEqual(comparison.segments);
      expect(result.current.compareTargetDraft?.version_id).toBe("draft-1");
    });
  });

  it("falls back to session answer versions when fetch fails", async () => {
    const fallbackDraft = buildAnswerVersion({ version_id: "fallback-draft", label: "Fallback Draft" });

    server.use(
      http.get(`${API_BASE_URL}/api/questions/:sessionId/drafts`, () =>
        HttpResponse.json({ detail: "Downstream unavailable" }, { status: 503 }),
      ),
    );

    const session = buildSession({ id: "session-fallback", answer_versions: [fallbackDraft] });
    const { result, rerender } = renderHook(({ currentSession }) => useDraftHistory({ session: currentSession }), {
      initialProps: { currentSession: session },
    });

    await waitFor(() => {
      expect(result.current.drafts).toEqual([fallbackDraft]);
      expect(result.current.selectedDraft?.version_id).toBe("fallback-draft");
    });

    rerender({ currentSession: null });

    await waitFor(() => {
      expect(result.current.drafts).toEqual([]);
      expect(result.current.selectedDraft).toBeNull();
      expect(result.current.compareEnabled).toBe(false);
    });
  });
});
