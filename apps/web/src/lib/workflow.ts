import { type EvidenceItem, type Session } from "@/lib/api";

export const SAMPLE_QUESTIONS = [
  "Describe your renewable energy investment strategy and how you create value over the hold period.",
  "How do you assess ESG risks during due diligence and portfolio monitoring?",
  "Provide examples of recent investments in solar or storage infrastructure.",
];

export const CONFIDENCE_WARNING_THRESHOLD = 0.7;

const CITATION_PATTERN = /\[([^[\]]+)\]/g;

export type CitationView = {
  answerText: string;
  citedEvidenceKeys: Set<string>;
  citationByEvidenceKey: Map<string, number>;
  citationKeyByNumber: Map<number, string>;
};

function normalizeToken(value: string): string {
  return value.trim().toLowerCase();
}

export function statusLabel(status: Session["status"]): string {
  switch (status) {
    case "awaiting_review":
      return "Awaiting Review";
    case "revision_requested":
      return "Revision Requested";
    case "awaiting_finalization":
      return "Finalization In Progress";
    case "approved":
      return "Approved · Locked";
    default:
      return "Draft";
  }
}

export function workflowSummary(status: Session["status"] | null): string {
  if (!status) return "Workflow: Not started";

  switch (status) {
    case "approved":
      return "Workflow: Approved (final)";
    case "awaiting_review":
      return "Workflow: Awaiting review";
    case "revision_requested":
      return "Workflow: Revision requested";
    case "awaiting_finalization":
      return "Workflow: Finalizing";
    default:
      return "Workflow: Draft in progress";
  }
}

export function nodeProgressLabel(session: Session | null): string {
  if (!session) return "Initializing workflow...";

  switch (session.current_node) {
    case "ask":
      return "Initializing workflow...";
    case "classify_and_plan":
      return "Planning retrieval...";
    case "classify_question":
      return "Classifying question...";
    case "adaptive_retrieve":
      return "Retrieving evidence adaptively...";
    case "retrieve_evidence":
      return "Retrieving evidence...";
    case "evaluate_evidence":
      return "Evaluating evidence sufficiency...";
    case "cross_reference_evidence":
      return "Cross-checking evidence...";
    case "draft_response":
      return "Drafting response...";
    case "polish_response":
      return "Polishing tone...";
    case "human_review":
      return session.status === "awaiting_review" ? "Draft ready for review." : "Waiting for review...";
    case "revise_response":
      return "Applying revision...";
    case "finalize_response":
      return "Finalizing response...";
    default:
      if (session.status === "awaiting_review") return "Draft ready for review.";
      if (session.status === "approved") return "Final answer approved.";
      return "Running workflow...";
  }
}

export function evidenceKey(item: EvidenceItem): string {
  if (item.chunk_id) {
    return item.chunk_id;
  }

  return `${normalizeToken(item.document_filename)}::${item.chunk_index}`;
}

function evidenceDocumentTokens(item: EvidenceItem): Set<string> {
  const tokens = new Set<string>();
  for (const raw of [item.document_filename, item.document_title, item.document_id]) {
    const value = normalizeToken(raw);
    if (!value) continue;
    tokens.add(value);

    const parts = value.split("/");
    const basename = parts[parts.length - 1];
    if (basename) {
      tokens.add(basename);
    }
  }

  return tokens;
}

function resolveCitationToEvidenceIndex(content: string, evidence: EvidenceItem[]): number | null {
  const citation = content.trim();
  if (!citation) return null;

  const indexedChunk = citation.match(/^(\d+)\s*#\s*chunk-(\d+)$/i);
  if (indexedChunk) {
    const sourceIndex = Number(indexedChunk[1]) - 1;
    return evidence[sourceIndex] ? sourceIndex : null;
  }

  const documentChunk = citation.match(/^(.+?)\s*#\s*chunk-(\d+)$/i);
  if (documentChunk) {
    const documentToken = normalizeToken(documentChunk[1]);
    const chunkIndex = Number(documentChunk[2]);

    const exact = evidence.findIndex((item) => {
      if (item.chunk_index !== chunkIndex) return false;
      return evidenceDocumentTokens(item).has(documentToken);
    });
    if (exact >= 0) return exact;

    const documentParts = documentToken.split("/");
    const documentBasename = documentParts[documentParts.length - 1];
    const fuzzy = evidence.findIndex((item) => {
      if (item.chunk_index !== chunkIndex) return false;

      const tokens = evidenceDocumentTokens(item);
      for (const token of tokens) {
        if (token.endsWith(documentBasename) || documentBasename.endsWith(token)) return true;
      }

      return false;
    });
    if (fuzzy >= 0) return fuzzy;

    const fallback = evidence.findIndex((item) => item.chunk_index === chunkIndex);
    return fallback >= 0 ? fallback : null;
  }

  const indexedOnly = citation.match(/^(\d+)$/);
  if (indexedOnly) {
    const sourceIndex = Number(indexedOnly[1]) - 1;
    return evidence[sourceIndex] ? sourceIndex : null;
  }

  return null;
}

export function buildCitationView(answerText: string, evidence: EvidenceItem[]): CitationView {
  if (!answerText) {
    return {
      answerText,
      citedEvidenceKeys: new Set<string>(),
      citationByEvidenceKey: new Map<string, number>(),
      citationKeyByNumber: new Map<number, string>(),
    };
  }

  const citedEvidenceKeys = new Set<string>();
  const citationByEvidenceKey = new Map<string, number>();
  const citationKeyByNumber = new Map<number, string>();
  let nextCitationNumber = 1;

  const normalizedAnswer = answerText.replace(CITATION_PATTERN, (fullMatch, content: string) => {
    const evidenceIndex = resolveCitationToEvidenceIndex(content, evidence);
    if (evidenceIndex === null) return fullMatch;

    const item = evidence[evidenceIndex];
    if (!item) return fullMatch;

    const key = evidenceKey(item);
    citedEvidenceKeys.add(key);

    if (!citationByEvidenceKey.has(key)) {
      citationByEvidenceKey.set(key, nextCitationNumber);
      citationKeyByNumber.set(nextCitationNumber, key);
      nextCitationNumber += 1;
    }

    return `[${citationByEvidenceKey.get(key)}]`;
  });

  return {
    answerText: normalizedAnswer,
    citedEvidenceKeys,
    citationByEvidenceKey,
    citationKeyByNumber,
  };
}

export type CitationToken =
  | {
      kind: "text";
      value: string;
    }
  | {
      kind: "citation";
      value: number;
      label: string;
    };

export function tokenizeNumberedCitations(answerText: string): CitationToken[] {
  const tokens: CitationToken[] = [];
  const citationPattern = /\[(\d+)\]/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = citationPattern.exec(answerText)) !== null) {
    if (match.index > cursor) {
      tokens.push({ kind: "text", value: answerText.slice(cursor, match.index) });
    }

    const citationNumber = Number(match[1]);
    tokens.push({ kind: "citation", value: citationNumber, label: match[0] });
    cursor = match.index + match[0].length;
  }

  if (cursor < answerText.length) {
    tokens.push({ kind: "text", value: answerText.slice(cursor) });
  }

  return tokens;
}

export function buildTimelineText(session: Session | null): string {
  if (!session) return "Submit a question to begin the workflow.";
  if (session.status === "approved") return "Final answer approved and locked.";
  if (session.status === "awaiting_review") return "Draft generated. Reviewer decision required.";
  if (session.status === "revision_requested") return "Revision requested. Submit feedback to continue.";
  return "Workflow running.";
}
