import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/__msw-health", () => HttpResponse.json({ ok: true })),
];
