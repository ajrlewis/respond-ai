"use client";

import { FormEvent, useEffect, useState } from "react";

import { WorkflowShell } from "@/components/workflow-shell";
import { fetchCurrentUser, login, logout, type AuthUser } from "@/lib/api";

type AuthStatus = "checking" | "unauthenticated" | "authenticated";

export default function Page() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>("checking");
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin1234");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadSession = async () => {
      setError(null);
      try {
        const user = await fetchCurrentUser();
        if (cancelled) return;

        if (user) {
          setCurrentUser(user);
          setAuthStatus("authenticated");
          return;
        }

        setCurrentUser(null);
        setAuthStatus("unauthenticated");
      } catch (err) {
        if (cancelled) return;
        setCurrentUser(null);
        setAuthStatus("unauthenticated");
        setError(err instanceof Error ? err.message : "Failed to check your session.");
      }
    };

    void loadSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const user = await login(username.trim(), password);
      setCurrentUser(user);
      setAuthStatus("authenticated");
      setPassword("");
    } catch (err) {
      setCurrentUser(null);
      setAuthStatus("unauthenticated");
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLogout = async () => {
    setIsLoggingOut(true);
    setError(null);

    try {
      await logout();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Logout failed.");
    } finally {
      setCurrentUser(null);
      setAuthStatus("unauthenticated");
      setIsLoggingOut(false);
      setPassword("");
    }
  };

  if (authStatus === "checking") {
    return (
      <main className="page-shell">
        <div className="backdrop-grid" />
        <section className="auth-shell">
          <div className="auth-panel">
            <h1>RespondAI</h1>
            <p className="auth-subtitle">Checking session...</p>
          </div>
        </section>
      </main>
    );
  }

  if (authStatus !== "authenticated") {
    return (
      <main className="page-shell">
        <div className="backdrop-grid" />
        <section className="auth-shell">
          <form className="auth-panel" onSubmit={handleLogin}>
            <h1>RespondAI Login</h1>
            <p className="auth-subtitle">Sign in to access the workflow.</p>
            <label className="field-label" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              disabled={isSubmitting}
              required
            />
            <label className="field-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={isSubmitting}
              required
            />
            {error ? <p className="form-error">{error}</p> : null}
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <WorkflowShell
      currentUsername={currentUser?.username ?? "admin"}
      isLoggingOut={isLoggingOut}
      onLogout={handleLogout}
    />
  );
}
