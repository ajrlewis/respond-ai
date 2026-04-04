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

export type AuthUser = {
  username: string;
};

type AuthResponse = {
  authenticated: boolean;
  user: AuthUser;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
