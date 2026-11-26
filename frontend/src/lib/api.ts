import type {
  Analysis,
  CreateAnalysisInput,
  HistoryItem,
  Place,
  Policy,
} from "../types";
import { clearSession, getAccessToken, getRefreshToken, saveTokens } from "./auth";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  fieldErrors: Record<string, string[] | string> | null;
  correlationId: string | null;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      detail?: string;
      fieldErrors?: Record<string, string[] | string> | null;
      correlationId?: string | null;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code ?? "request_failed";
    this.detail = options.detail ?? message;
    this.fieldErrors = options.fieldErrors ?? null;
    this.correlationId = options.correlationId ?? null;
  }
}

/**
 * Exchange the stored refresh token for a new access token.
 *
 * Uses a bare fetch (not `request`) so a failed refresh can never recurse
 * through the 401 retry path.
 */
async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  try {
    const response = await fetch(`${API_BASE}/auth/token/refresh/`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!response.ok) return null;
    const body = (await response.json()) as { access?: string; refresh?: string };
    if (!body.access) return null;
    saveTokens({ access: body.access, refresh: body.refresh });
    return body.access;
  } catch {
    return null;
  }
}

async function request<T>(path: string, init?: RequestInit, allowRefresh = true): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");

  const isAuthPath = path.startsWith("/auth/");
  let token = getAccessToken();
  // Restore an expired session from the refresh token before the request so a
  // returning user does not silently fall back to anonymous access.
  if (!token && allowRefresh && !isAuthPath && getRefreshToken()) {
    token = await refreshAccessToken();
    if (!token) clearSession();
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Cannot reach the route-safety API.", {
      status: 0,
      code: "network_error",
      detail: "Check your connection and confirm the Django API is running.",
    });
  }

  // Access tokens are short-lived; transparently refresh once, then retry.
  if (response.status === 401 && allowRefresh && !path.startsWith("/auth/")) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return request<T>(path, init, false);
    clearSession();
  }

  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("Content-Type") ?? "";
  const body = contentType.includes("json") ? await response.json() : null;

  if (!response.ok) {
    const detail =
      (body && typeof body.detail === "string" && body.detail) ||
      (body && typeof body.message === "string" && body.message) ||
      `Request failed (${response.status}).`;
    throw new ApiError(detail, {
      status: response.status,
      code: body?.code,
      detail,
      fieldErrors: body?.errors ?? null,
      correlationId: body?.correlation_id ?? response.headers.get("X-Correlation-ID"),
    });
  }

  return body as T;
}

export function createAnalysis(input: CreateAnalysisInput): Promise<Analysis> {
  return request<Analysis>("/analyses/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getAnalysis(id: string): Promise<Analysis> {
  return request<Analysis>(`/analyses/${id}/`);
}

export function deleteAnalysis(id: string): Promise<void> {
  return request<void>(`/analyses/${id}/`, { method: "DELETE" });
}

export function listAnalyses(): Promise<{
  results: HistoryItem[];
  next: string | null;
  previous: string | null;
}> {
  return request("/analyses/?page_size=10");
}

export function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  return request<{ results: Place[] }>(
    `/places/?q=${encodeURIComponent(query)}`,
    { signal },
  ).then((payload) => payload.results);
}

export function fetchPolicy(): Promise<Policy> {
  return request<Policy>("/policy/");
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export function login(username: string, password: string): Promise<AuthTokens> {
  return request<AuthTokens>("/auth/token/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function register(
  username: string,
  password: string,
  email?: string,
): Promise<AuthTokens> {
  return request<AuthTokens>("/auth/register/", {
    method: "POST",
    body: JSON.stringify({ username, password, email }),
  });
}

export function refreshToken(refresh: string): Promise<{ access: string }> {
  return request<{ access: string }>("/auth/token/refresh/", {
    method: "POST",
    body: JSON.stringify({ refresh }),
  });
}

export interface AuthUser {
  authenticated: boolean;
  id?: number;
  username?: string;
  email?: string;
}

export function fetchMe(): Promise<AuthUser> {
  return request<AuthUser>("/auth/me/");
}
