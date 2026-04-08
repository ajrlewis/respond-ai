import { describe, expect, it } from "vitest";

import { extractQuestions, fallbackStages } from "@/components/review-v2/review-v2-shell-utils";

describe("review-v2-shell-utils", () => {
  it("extracts unique question-like lines from uploaded text", () => {
    const input = `
      1. What is your investment strategy?
      2. What is your investment strategy?
      - Provide a detailed summary of your risk controls and governance process across the portfolio.
      Short line
      * How do you monitor ESG compliance?
    `;

    const questions = extractQuestions(input);
    expect(questions).toEqual([
      "What is your investment strategy?",
      "Provide a detailed summary of your risk controls and governance process across the portfolio.",
      "How do you monitor ESG compliance?",
    ]);
  });

  it("caps extracted questions at twenty entries", () => {
    const manyQuestions = Array.from(
      { length: 30 },
      (_, index) => `${index + 1}. How does workflow step ${index + 1} operate?`,
    ).join("\n");

    const questions = extractQuestions(manyQuestions);
    expect(questions).toHaveLength(20);
    expect(questions[0]).toBe("How does workflow step 1 operate?");
    expect(questions[19]).toBe("How does workflow step 20 operate?");
  });

  it("returns a human-readable fallback stage sequence", () => {
    expect(fallbackStages()).toEqual([
      { id: "retrieve_context", label: "Retrieve supporting material", status: "running" },
      { id: "rank_evidence", label: "Rank evidence", status: "idle" },
      { id: "draft_response", label: "Draft response", status: "idle" },
      { id: "validate_grounding", label: "Review citations", status: "idle" },
    ]);
  });
});
