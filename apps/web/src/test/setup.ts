import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";

import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { installMockEventSource, resetMockEventSources } from "@/test/mocks/event-source";
import { server } from "@/test/msw/server";

installMockEventSource();

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  resetMockEventSources();
  vi.restoreAllMocks();
});

afterAll(() => {
  server.close();
});
