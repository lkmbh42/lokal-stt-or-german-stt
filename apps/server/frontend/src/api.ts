/**
 * API client with JWT handling: access token attached to every request,
 * transparent one-shot refresh on 401, hard logout when the refresh fails.
 *
 * Tokens live in localStorage — a documented tradeoff for this internal
 * tool (XSS in the app would expose them; the Phase 4 security pass revisits
 * httpOnly-cookie transport).
 */

const ACCESS_KEY = "stt.access";
const REFRESH_KEY = "stt.refresh";

export class AuthExpiredError extends Error {
  constructor() {
    super("Sitzung abgelaufen");
  }
}

export function isLoggedIn(): boolean {
  return localStorage.getItem(ACCESS_KEY) !== null;
}

export function logout(): void {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  const accessToken = localStorage.getItem(ACCESS_KEY);
  if (refreshToken && accessToken) {
    // best-effort server-side revocation; local cleanup happens regardless
    void fetch("/api/auth/logout", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).catch(() => undefined);
  }
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function login(username: string, password: string): Promise<void> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((data) => data.detail)
      .catch(() => null);
    throw new Error(typeof detail === "string" ? detail : "Anmeldung fehlgeschlagen");
  }
  const pair = await response.json();
  localStorage.setItem(ACCESS_KEY, pair.access_token);
  localStorage.setItem(REFRESH_KEY, pair.refresh_token);
}

async function tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return false;
  const response = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;
  const pair = await response.json();
  localStorage.setItem(ACCESS_KEY, pair.access_token);
  localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  return true;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const call = () =>
    fetch(path, {
      ...init,
      headers: {
        ...(init.headers ?? {}),
        Authorization: `Bearer ${localStorage.getItem(ACCESS_KEY) ?? ""}`,
      },
    });
  let response = await call();
  if (response.status === 401) {
    if (await tryRefresh()) {
      response = await call();
    } else {
      logout();
      throw new AuthExpiredError();
    }
  }
  return response;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    const detail = await response
      .json()
      .then((data) => data.detail)
      .catch(() => null);
    throw new Error(
      typeof detail === "string" ? detail : `Serverfehler (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

/** Export downloads need the Authorization header, so plain <a href> won't
 * do — fetch the blob and hand it to the browser as a download. */
export async function downloadExport(jobId: string, format: string, filename: string) {
  const response = await apiFetch(`/api/jobs/${jobId}/export?format=${format}`);
  if (!response.ok) throw new Error(`Export fehlgeschlagen (${response.status})`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
