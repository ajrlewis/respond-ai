export type Tone = "concise" | "detailed" | "formal";
export type SessionStatus =
  | "draft"
  | "awaiting_review"
  | "revision_requested"
  | "awaiting_finalization"
  | "approved";

export type EvidenceItem = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_filename: string;
  chunk_index: number;
  text: string;
  score: number;
  retrieval_method: string;
  excluded_by_reviewer?: boolean;
  metadata: Record<string, unknown>;
};

export type Confidence = {
  score: number | null;
  compliance_status: "passed" | "needs_review" | "unknown";
  model_notes: string;
  retrieval_notes: string;
  evidence_gaps: string[];
  retrieval_strategy?: string | null;
  coverage?: "strong" | "partial" | "weak" | "unknown";
  recommended_action?: "proceed" | "proceed_with_caveats" | "retrieve_more" | "unknown";
  selected_chunk_ids?: string[];
  rejected_chunk_ids?: string[];
  notes_for_drafting?: string[];
};

export type AnswerVersion = {
  version_id: string;
  version_number: number;
  label: string;
  stage: "draft" | "revision" | "final";
  answer_text: string;
  content: string;
  status: "draft" | "approved" | "historical";
  is_current: boolean;
  is_approved: boolean;
  revision_feedback: string | null;
  included_chunk_ids: string[];
  excluded_chunk_ids: string[];
  question_type: string | null;
  confidence_notes: string | null;
  confidence_score: number | null;
  created_at: string;
};

export type DraftDiffSegment = {
  kind: "same" | "added" | "removed";
  text: string;
};

export type DraftComparison = {
  left: AnswerVersion;
  right: AnswerVersion;
  segments: DraftDiffSegment[];
};

export type Session = {
  id: string;
  question_text: string;
  question_type: string | null;
  tone: Tone;
  status: SessionStatus;
  current_node: string | null;
  retrieval_strategy_used?: string | null;
  retry_count?: number;
  draft_answer: string | null;
  final_answer: string | null;
  final_version_number: number | null;
  approved_at: string | null;
  reviewer_action: string | null;
  reviewer_id: string | null;
  evidence_gap_count: number;
  requires_gap_acknowledgement: boolean;
  evidence_gaps_acknowledged: boolean;
  evidence_gaps_acknowledged_at: string | null;
  confidence_notes: string | null;
  confidence: Confidence;
  retrieval_plan?: Record<string, unknown>;
  evidence_evaluation?: Record<string, unknown>;
  evidence: EvidenceItem[];
  answer_versions: AnswerVersion[];
  final_audit: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WorkflowStateEvent = {
  reason: string;
  timestamp?: string;
  node?: string;
  status?: string;
  error?: string;
  session?: Session;
  stream_ref?: string;
};

export type AuthUser = {
  username: string;
};

export type WorkspaceClientManifest = {
  client_id: string;
  display_name: string;
  environment_label: string;
  enabled_features: string[];
};

export type WorkspaceBrandingConfig = {
  company_name: string;
  logo_src: string | null;
  workspace_title: string;
  workspace_subtitle: string;
  start_title: string;
  start_subtitle: string;
};

export type WorkspaceClientConfig = {
  client: WorkspaceClientManifest;
  branding: WorkspaceBrandingConfig;
  workspace: Record<string, unknown>;
};

export type ResponseQuestion = {
  id: string;
  order_index: number;
  extracted_text: string;
  normalized_title: string | null;
};

export type ResponseSection = {
  id: string;
  question_id: string;
  order_index: number;
  content_markdown: string;
  confidence_score: number | null;
  coverage_score: number | null;
  evidence_refs: EvidenceItem[];
};

export type ResponseVersionSummary = {
  id: string;
  version_number: number;
  label: string;
  created_by: string | null;
  parent_version_id: string | null;
  is_final: boolean;
  created_at: string;
};

export type ResponseVersion = ResponseVersionSummary & {
  sections: ResponseSection[];
};

export type ResponseDocument = {
  id: string;
  title: string;
  source_filename: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  questions: ResponseQuestion[];
  versions: ResponseVersionSummary[];
  selected_version: ResponseVersion | null;
};

export type ResponseVersionComparison = {
  left: ResponseVersionSummary;
  right: ResponseVersionSummary;
  segments: DraftDiffSegment[];
  section_diffs: Array<{
    question_id: string;
    question_text: string;
    segments: DraftDiffSegment[];
  }>;
};

export type ResponseSaveSectionInput = {
  question_id: string;
  content_markdown: string;
  evidence_refs?: EvidenceItem[];
  confidence_score?: number | null;
  coverage_score?: number | null;
};

export type AIReviseResponseDocumentResult = {
  base_version_id: string;
  revised_sections: ResponseSaveSectionInput[];
};

export type ResponseDocumentWorkflowEvent = {
  reason: string;
  timestamp?: string;
  node?: string;
  status?: string;
  error?: string;
  metadata?: Record<string, unknown>;
};

type AuthResponse = {
  authenticated: boolean;
  user: AuthUser;
};

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

function resolveApiBaseUrl(): string {
  const configured = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").trim();
  if (configured) {
    return normalizeBaseUrl(configured);
  }

  // In browser/runtime default to same-origin so Next.js rewrites can proxy API calls.
  // Tests still use explicit localhost handlers.
  if (process.env.NODE_ENV === "test") {
    return "http://localhost:8000";
  }

  return "";
}

const API_BASE_URL = resolveApiBaseUrl();

function resolveSseBaseUrl(): string {
  const configuredSse = (process.env.NEXT_PUBLIC_API_SSE_BASE_URL ?? "").trim();
  if (configuredSse) {
    return normalizeBaseUrl(configuredSse);
  }
  if (API_BASE_URL) {
    return API_BASE_URL;
  }
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return `${protocol}//${hostname}:8000`;
    }
  }
  return "";
}

const SSE_BASE_URL = resolveSseBaseUrl();

async function parseErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed with status ${response.status}`;

  try {
    const body = (await response.json()) as unknown;
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
    }
    return fallback;
  } catch {
    const text = await response.text();
    return text || fallback;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as T;
}

export async function askQuestion(questionText: string, tone: Tone, threadId?: string): Promise<Session> {
  const payload = await request<{ session: Session }>("/api/questions/ask", {
    method: "POST",
    body: JSON.stringify({ question_text: questionText, tone, thread_id: threadId }),
  });

  return payload.session;
}

export async function reviewSession(
  sessionId: string,
  reviewerAction: "approve" | "revise",
  options?: {
    reviewerId?: string;
    reviewComments?: string;
    excludedEvidenceKeys?: string[];
    reviewedEvidenceGaps?: boolean;
    evidenceGapsAcknowledged?: boolean;
  },
): Promise<Session> {
  const evidenceGapsAcknowledged = options?.evidenceGapsAcknowledged ?? options?.reviewedEvidenceGaps ?? false;
  const payload = await request<{ session: Session }>(`/api/questions/${sessionId}/review`, {
    method: "POST",
    body: JSON.stringify({
      reviewer_action: reviewerAction,
      reviewer_id: options?.reviewerId,
      review_comments: options?.reviewComments,
      excluded_evidence_keys: options?.excludedEvidenceKeys ?? [],
      reviewed_evidence_gaps: evidenceGapsAcknowledged,
      evidence_gaps_acknowledged: evidenceGapsAcknowledged,
    }),
  });

  return payload.session;
}

export async function fetchSession(sessionId: string): Promise<Session> {
  return request<Session>(`/api/questions/${sessionId}`);
}

export async function fetchSessionByThreadId(threadId: string): Promise<Session | null> {
  const response = await fetch(`${API_BASE_URL}/api/questions/thread/${encodeURIComponent(threadId)}`, {
    credentials: "include",
    cache: "no-store",
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as Session;
}

export function openSessionEventsStream(sessionId: string): EventSource {
  return new EventSource(`${SSE_BASE_URL}/api/questions/${encodeURIComponent(sessionId)}/events`, {
    withCredentials: true,
  });
}

export function openThreadEventsStream(threadId: string): EventSource {
  return new EventSource(`${SSE_BASE_URL}/api/questions/thread/${encodeURIComponent(threadId)}/events`, {
    withCredentials: true,
  });
}

export function openResponseDocumentEventsStream(documentId: string): EventSource {
  return new EventSource(
    `${SSE_BASE_URL}/api/response-documents/${encodeURIComponent(documentId)}/events`,
    {
      withCredentials: true,
    },
  );
}

export async function fetchDrafts(sessionId: string): Promise<AnswerVersion[]> {
  return request<AnswerVersion[]>(`/api/questions/${sessionId}/drafts`);
}

export async function fetchDraft(sessionId: string, draftId: string): Promise<AnswerVersion> {
  return request<AnswerVersion>(`/api/questions/${sessionId}/drafts/${encodeURIComponent(draftId)}`);
}

export async function compareDrafts(sessionId: string, leftId: string, rightId: string): Promise<DraftComparison> {
  const query = new URLSearchParams({ left: leftId, right: rightId });
  return request<DraftComparison>(`/api/questions/${sessionId}/drafts/compare?${query.toString()}`);
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const payload = await request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  return payload.user;
}

export async function logout(): Promise<void> {
  await request<{ authenticated: boolean }>("/auth/logout", {
    method: "POST",
  });
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    credentials: "include",
    cache: "no-store",
  });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  const payload = (await response.json()) as AuthResponse;
  return payload.user;
}

export async function fetchWorkspaceClientConfig(): Promise<WorkspaceClientConfig | null> {
  const response = await fetch(`${API_BASE_URL}/api/client-config/workspace`, {
    credentials: "include",
    cache: "no-store",
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as WorkspaceClientConfig;
}

export async function createResponseDocument(payload: {
  title?: string;
  sourceFilename?: string;
  sourceText?: string;
  questions?: string[];
  useExampleQuestions?: boolean;
  createdBy?: string;
}): Promise<ResponseDocument> {
  return request<ResponseDocument>("/api/response-documents", {
    method: "POST",
    body: JSON.stringify({
      title: payload.title,
      source_filename: payload.sourceFilename,
      source_text: payload.sourceText,
      questions: payload.questions ?? [],
      use_example_questions: payload.useExampleQuestions ?? false,
      created_by: payload.createdBy,
    }),
  });
}

export async function createSampleResponseDocument(): Promise<ResponseDocument> {
  return request<ResponseDocument>("/api/response-documents/sample", {
    method: "POST",
  });
}

export async function fetchResponseDocument(
  documentId: string,
  options?: { selectedVersionId?: string | null },
): Promise<ResponseDocument> {
  const query = new URLSearchParams();
  if (options?.selectedVersionId) {
    query.set("selected_version_id", options.selectedVersionId);
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return request<ResponseDocument>(
    `/api/response-documents/${encodeURIComponent(documentId)}${suffix}`,
  );
}

export async function generateResponseDocument(
  documentId: string,
  options?: { tone?: Tone; createdBy?: string; runId?: string },
): Promise<ResponseDocument> {
  return request<ResponseDocument>(
    `/api/response-documents/${encodeURIComponent(documentId)}/generate`,
    {
      method: "POST",
      body: JSON.stringify({
        tone: options?.tone ?? "formal",
        created_by: options?.createdBy,
        run_id: options?.runId,
      }),
    },
  );
}

export async function saveResponseDocumentVersion(
  documentId: string,
  payload: {
    label?: string;
    basedOnVersionId?: string | null;
    createdBy?: string;
    sections: ResponseSaveSectionInput[];
  },
): Promise<ResponseDocument> {
  return request<ResponseDocument>(
    `/api/response-documents/${encodeURIComponent(documentId)}/versions`,
    {
      method: "POST",
      body: JSON.stringify({
        label: payload.label,
        based_on_version_id: payload.basedOnVersionId ?? null,
        created_by: payload.createdBy,
        sections: payload.sections,
      }),
    },
  );
}

export async function listResponseDocumentVersions(
  documentId: string,
): Promise<ResponseVersionSummary[]> {
  return request<ResponseVersionSummary[]>(
    `/api/response-documents/${encodeURIComponent(documentId)}/versions`,
  );
}

export async function approveResponseDocumentVersion(
  documentId: string,
  versionId: string,
): Promise<ResponseDocument> {
  return request<ResponseDocument>(
    `/api/response-documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/approve`,
    { method: "POST" },
  );
}

export async function deleteResponseDocumentVersion(
  documentId: string,
  versionId: string,
): Promise<ResponseDocument> {
  return request<ResponseDocument>(
    `/api/response-documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}`,
    { method: "DELETE" },
  );
}

export async function compareResponseDocumentVersions(
  documentId: string,
  leftVersionId: string,
  rightVersionId: string,
): Promise<ResponseVersionComparison> {
  const query = new URLSearchParams({
    left_version_id: leftVersionId,
    right_version_id: rightVersionId,
  });
  return request<ResponseVersionComparison>(
    `/api/response-documents/${encodeURIComponent(documentId)}/compare?${query.toString()}`,
  );
}

export async function aiReviseResponseDocument(
  documentId: string,
  payload: {
    instruction: string;
    tone?: Tone;
    baseVersionId?: string | null;
    questionId?: string | null;
    selectedText?: string | null;
    runId?: string;
  },
): Promise<AIReviseResponseDocumentResult> {
  return request<AIReviseResponseDocumentResult>(
    `/api/response-documents/${encodeURIComponent(documentId)}/ai-revise`,
    {
      method: "POST",
      body: JSON.stringify({
        instruction: payload.instruction,
        tone: payload.tone ?? "formal",
        base_version_id: payload.baseVersionId ?? null,
        question_id: payload.questionId ?? null,
        selected_text: payload.selectedText ?? null,
        run_id: payload.runId,
      }),
    },
  );
}
