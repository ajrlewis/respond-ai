"use client";

import { useEffect, useState } from "react";

import { ReviewV2Shell } from "@/components/review-v2";
import { fetchCurrentUser, type AuthUser } from "@/lib/api";

export default function ReviewV2Page() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadUser = async () => {
      try {
        const user = await fetchCurrentUser();
        if (cancelled) return;
        setCurrentUser(user);
      } catch {
        if (cancelled) return;
        setCurrentUser(null);
      }
    };

    void loadUser();
    return () => {
      cancelled = true;
    };
  }, []);

  return <ReviewV2Shell currentUsername={currentUser?.username ?? "guest"} />;
}
