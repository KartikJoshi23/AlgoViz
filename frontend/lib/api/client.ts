/**
 * Typed REST client generated from the backend's OpenAPI document.
 *
 *   const { data, error } = await api.GET("/api/v1/market/features", { params: { query: { symbol } } });
 *
 * `paths` comes from `lib/api/schema.d.ts` (npm run types). Never hand-write
 * response shapes — regenerate.
 */
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? API_URL.replace(/^http/, "ws") + "/ws";

export const api = createClient<paths>({ baseUrl: API_URL });

/**
 * The admin token for changes on a server that gates them (production). It is
 * kept in this browser only, never in the shared preferences, and sent as a
 * bearer credential with every request once set.
 */
const TOKEN_KEY = "algoviz.adminToken";

export function readAdminToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // storage blocked (private mode, sandboxed frames)
  }
}

const TOKEN_EVENT = "algoviz:admin-token";

export function writeAdminToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage blocked: the token lives for this page only
  }
  window.dispatchEvent(new Event(TOKEN_EVENT));
}

/** For `useSyncExternalStore`: changes from this tab (the event) and from others (`storage`). */
export function subscribeAdminToken(onChange: () => void): () => void {
  window.addEventListener(TOKEN_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(TOKEN_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

api.use({
  onRequest({ request }) {
    const token = typeof window === "undefined" ? null : readAdminToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
});

export type { paths, components } from "./schema";
