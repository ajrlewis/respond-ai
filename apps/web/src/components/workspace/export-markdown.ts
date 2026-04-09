import type { EvidenceItem, ResponseDocument } from "@/lib/api";

const INLINE_CITATION_PATTERN = /\[(\d+)\]/g;

function sanitizeFilenamePart(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

function sourceLabel(item: EvidenceItem): string {
  const filename = item.document_filename.trim();
  if (filename) return filename;
  const title = item.document_title.trim();
  if (title) return title;
  return item.document_id;
}

function extractOrderedCitationNumbers(contentMarkdown: string): number[] {
  const ordered: number[] = [];
  const seen = new Set<number>();
  for (const match of contentMarkdown.matchAll(INLINE_CITATION_PATTERN)) {
    const parsed = Number.parseInt(match[1] ?? "", 10);
    if (!Number.isFinite(parsed) || parsed <= 0 || seen.has(parsed)) continue;
    ordered.push(parsed);
    seen.add(parsed);
  }
  return ordered;
}

function formatReferenceLine(citationNumber: number, evidence: EvidenceItem): string {
  const details: string[] = [];
  if (Number.isFinite(evidence.chunk_index)) details.push(`chunk ${evidence.chunk_index}`);
  if (evidence.retrieval_method) details.push(evidence.retrieval_method);
  if (Number.isFinite(evidence.score)) details.push(`score ${evidence.score.toFixed(2)}`);
  const detailSuffix = details.length ? ` (${details.join(", ")})` : "";
  return `[${citationNumber}] ${sourceLabel(evidence)}${detailSuffix}`;
}

export function buildExportFilename(document: ResponseDocument, versionNumber: number): string {
  const titlePart = sanitizeFilenamePart(document.title.trim());
  const base = titlePart || "response";
  return `${base}-v${versionNumber}.md`;
}

export function buildExportMarkdown(
  document: ResponseDocument,
  selectedVersion: NonNullable<ResponseDocument["selected_version"]>,
): string {
  const title = document.title.trim() || "Response Draft";
  const sectionByQuestionId = new Map(selectedVersion.sections.map((section) => [section.question_id, section] as const));
  const questionBlocks = [...document.questions]
    .sort((left, right) => left.order_index - right.order_index)
    .map((question, index) => {
      const section = sectionByQuestionId.get(question.id);
      const answer = section?.content_markdown.trim() ?? "";
      const answerBody = answer || "_No answer provided._";
      const block = [`## Question ${index + 1}: ${question.extracted_text}`, "", answerBody];
      const evidenceRefs = section?.evidence_refs ?? [];
      if (!evidenceRefs.length) {
        return block.join("\n");
      }

      const citations = extractOrderedCitationNumbers(answerBody);
      const referenceNumbers = citations.length ? citations : evidenceRefs.map((_, referenceIndex) => referenceIndex + 1);
      const references = referenceNumbers
        .map((citationNumber) => {
          const evidence = evidenceRefs[citationNumber - 1];
          if (!evidence) return null;
          return formatReferenceLine(citationNumber, evidence);
        })
        .filter((line): line is string => !!line);
      if (!references.length) {
        return block.join("\n");
      }

      return [...block, "", "### References", "", ...references, ""].join("\n");
    });
  const exportedAt = new Date().toISOString();

  return [
    `# ${title}`,
    "",
    `- Version: ${selectedVersion.version_number}`,
    `- Exported: ${exportedAt}`,
    "",
    ...questionBlocks,
    "",
  ].join("\n");
}
