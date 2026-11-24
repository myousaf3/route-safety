import type {
  Analysis,
  CreateAnalysisInput,
  HistoryItem,
  Place,
  Policy,
} from "../types";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");

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
