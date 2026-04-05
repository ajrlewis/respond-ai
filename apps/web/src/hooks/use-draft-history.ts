import { useEffect, useMemo, useState } from "react";

import {
  compareDrafts,
  fetchDrafts,
  type AnswerVersion,
  type DraftDiffSegment,
  type Session,
} from "@/lib/api";

type UseDraftHistoryArgs = {
  session: Session | null;
};

export type UseDraftHistoryResult = {
  drafts: AnswerVersion[];
  currentDraft: AnswerVersion | null;
  selectedDraft: AnswerVersion | null;
  compareTargetDraft: AnswerVersion | null;
  selectedDraftId: string | null;
  compareDraftId: string;
  compareEnabled: boolean;
  compareSegments: DraftDiffSegment[];
  isCompareMode: boolean;
  isViewingCurrentDraft: boolean;
  isViewingHistoricalDraft: boolean;
  viewingLabel: string;
  latestSnapshotTimestamp: string | null;
  setSelectedDraftId: (draftId: string | null) => void;
  setCompareSelection: (draftId: string) => void;
  pinToLatestDraft: () => void;
  resetHistory: () => void;
};

export function useDraftHistory({ session }: UseDraftHistoryArgs): UseDraftHistoryResult {
  const [drafts, setDrafts] = useState<AnswerVersion[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [compareEnabled, setCompareEnabled] = useState(false);
  const [compareDraftId, setCompareDraftId] = useState("");
  const [compareSegments, setCompareSegments] = useState<DraftDiffSegment[]>([]);

  const currentDraft = useMemo(
    () => drafts.find((draft) => draft.is_current) ?? drafts[drafts.length - 1] ?? null,
    [drafts],
  );

  const selectedDraft = useMemo(() => {
    if (!drafts.length) return null;
    if (selectedDraftId) {
      const selected = drafts.find((draft) => draft.version_id === selectedDraftId);
      if (selected) return selected;
    }
    return currentDraft;
  }, [currentDraft, drafts, selectedDraftId]);

  const compareTargetDraft = useMemo(
    () => drafts.find((draft) => draft.version_id === compareDraftId) ?? null,
    [compareDraftId, drafts],
  );

  const isCompareMode = compareEnabled && !!selectedDraft && !!compareTargetDraft;
  const isViewingCurrentDraft = selectedDraft ? selectedDraft.is_current : true;
  const isViewingHistoricalDraft = selectedDraft ? !selectedDraft.is_current : false;

  const viewingLabel = selectedDraft
    ? `Draft ${selectedDraft.version_number}${selectedDraft.is_current ? " (current)" : ""}`
    : session?.status === "approved"
      ? "Final Response (locked)"
      : "Current draft";

  const latestSnapshotTimestamp = currentDraft?.created_at ?? session?.updated_at ?? null;

  useEffect(() => {
    if (!session) {
      setDrafts([]);
      setSelectedDraftId(null);
      setCompareEnabled(false);
      setCompareDraftId("");
      setCompareSegments([]);
      return;
    }

    let cancelled = false;

    const hydrateDrafts = async () => {
      try {
        const fetched = await fetchDrafts(session.id);
        if (cancelled) return;
        setDrafts(fetched);
      } catch {
        if (cancelled) return;
        setDrafts(session.answer_versions ?? []);
      }
    };

    void hydrateDrafts();

    return () => {
      cancelled = true;
    };
  }, [session?.id, session?.updated_at]);

  useEffect(() => {
    if (!drafts.length) {
      setSelectedDraftId(null);
      setCompareEnabled(false);
      setCompareDraftId("");
      return;
    }

    const hasSelected = selectedDraftId ? drafts.some((draft) => draft.version_id === selectedDraftId) : false;
    if (!hasSelected) {
      const latest = drafts.find((draft) => draft.is_current) ?? drafts[drafts.length - 1];
      setSelectedDraftId(latest?.version_id ?? null);
    }

    if (compareDraftId && !drafts.some((draft) => draft.version_id === compareDraftId)) {
      setCompareDraftId("");
      setCompareEnabled(false);
    }
  }, [compareDraftId, drafts, selectedDraftId]);

  useEffect(() => {
    if (!compareEnabled) {
      setCompareSegments([]);
      return;
    }

    if (!session || !selectedDraft) {
      setCompareSegments([]);
      return;
    }

    let targetId = compareDraftId;
    if (!targetId) {
      const previous = [...drafts]
        .filter((draft) => draft.version_number < selectedDraft.version_number)
        .sort((a, b) => b.version_number - a.version_number)[0];
      targetId = previous?.version_id ?? "";
      if (targetId) {
        setCompareDraftId(targetId);
      } else {
        setCompareEnabled(false);
        setCompareSegments([]);
        return;
      }
    }

    if (targetId === selectedDraft.version_id) {
      setCompareSegments([]);
      return;
    }

    let cancelled = false;

    const loadComparison = async () => {
      try {
        const comparison = await compareDrafts(session.id, targetId, selectedDraft.version_id);
        if (cancelled) return;
        setCompareSegments(comparison.segments);
      } catch {
        if (cancelled) return;
        setCompareSegments([]);
      }
    };

    void loadComparison();

    return () => {
      cancelled = true;
    };
  }, [compareDraftId, compareEnabled, drafts, selectedDraft?.version_id, selectedDraft?.version_number, session?.id]);

  function setCompareSelection(draftId: string) {
    if (!draftId) {
      setCompareEnabled(false);
      setCompareDraftId("");
      setCompareSegments([]);
      return;
    }

    setCompareEnabled(true);
    setCompareDraftId(draftId);
  }

  function pinToLatestDraft() {
    setSelectedDraftId(null);
    setCompareEnabled(false);
    setCompareDraftId("");
    setCompareSegments([]);
  }

  function resetHistory() {
    setDrafts([]);
    pinToLatestDraft();
  }

  return {
    drafts,
    currentDraft,
    selectedDraft,
    compareTargetDraft,
    selectedDraftId,
    compareDraftId,
    compareEnabled,
    compareSegments,
    isCompareMode,
    isViewingCurrentDraft,
    isViewingHistoricalDraft,
    viewingLabel,
    latestSnapshotTimestamp,
    setSelectedDraftId,
    setCompareSelection,
    pinToLatestDraft,
    resetHistory,
  };
}
