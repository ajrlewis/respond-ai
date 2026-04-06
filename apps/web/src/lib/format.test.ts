import { describe, expect, it, vi } from "vitest";

import {
  formatComplianceStatus,
  formatDraftState,
  formatDraftTimestamp,
  formatQuestionType,
  formatRetrievalMethod,
} from "@/lib/format";

describe("format helpers", () => {
  it("formats question and state labels with sensible fallbacks", () => {
    expect(formatQuestionType(null)).toBe("Unclassified");
    expect(formatQuestionType("needs_review")).toBe("Needs Review");
    expect(formatComplianceStatus("unknown")).toBe("Unknown");
    expect(formatDraftState("approved")).toBe("Approved");
  });

  it("formats retrieval methods with explicit semantic and keyword labels", () => {
    expect(formatRetrievalMethod("semantic")).toBe("Semantic match");
    expect(formatRetrievalMethod("keyword")).toBe("Keyword match");
    expect(formatRetrievalMethod("hybrid")).toBe("Hybrid");
    expect(formatRetrievalMethod("")).toBe("Unknown method");
  });

  it("passes through invalid timestamps and formats valid timestamps", () => {
    const toLocaleStringSpy = vi.spyOn(Date.prototype, "toLocaleString").mockReturnValue("formatted-date");

    expect(formatDraftTimestamp("not-a-date")).toBe("not-a-date");
    expect(formatDraftTimestamp("2026-01-01T00:00:00.000Z")).toBe("formatted-date");

    toLocaleStringSpy.mockRestore();
  });
});
