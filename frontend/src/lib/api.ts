import type {
  AuditLogResponse,
  AuthResponse,
  ChatHistoryItem,
  ChatSuggestion,
  DataSourceItem,
} from "@/types";

export const API_BASE_URL = "/api";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function createHeaders(token?: string, headers?: HeadersInit, hasBody?: boolean): Headers {
  const nextHeaders = new Headers(headers ?? {});
  if (token) {
    nextHeaders.set("Authorization", `Bearer ${token}`);
  }
  if (hasBody && !nextHeaders.has("Content-Type")) {
    nextHeaders.set("Content-Type", "application/json");
  }
  return nextHeaders;
}

async function parsePayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function payloadMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }
  if (typeof payload === "object" && payload !== null) {
    const record = payload as Record<string, unknown>;
    if (typeof record.error === "string" && record.error.trim()) {
      return record.error;
    }
    if (typeof record.message === "string" && record.message.trim()) {
      return record.message;
    }
  }
  return fallback;
}

export async function apiRequest<T>(
  path: string,
  options: {
    method?: string;
    token?: string;
    body?: unknown;
    signal?: AbortSignal;
    headers?: HeadersInit;
  } = {}
): Promise<T> {
  const { method = "GET", token, body, signal, headers } = options;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    signal,
    headers: createHeaders(token, headers, body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const payload = await parsePayload(response);

  if (!response.ok) {
    const code =
      typeof payload === "object" && payload !== null && typeof (payload as Record<string, unknown>).code === "string"
        ? ((payload as Record<string, unknown>).code as string)
        : undefined;
    throw new ApiError(payloadMessage(payload, `Request failed (${response.status})`), response.status, code);
  }

  return payload as T;
}

export function loginWithMockGoogle(email: string): Promise<AuthResponse> {
  return apiRequest<AuthResponse>("/auth/google", {
    method: "POST",
    body: {
      google_token: `mock:${email}`,
    },
  });
}

export function logoutSession(token: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/auth/logout", {
    method: "POST",
    token,
  });
}

export function getChatSuggestions(token: string): Promise<ChatSuggestion[]> {
  return apiRequest<ChatSuggestion[]>("/chat/suggestions", { token });
}

export function getChatHistory(token: string): Promise<ChatHistoryItem[]> {
  return apiRequest<ChatHistoryItem[]>("/chat/history", { token });
}

export function getAuditLog(
  token: string,
  page: number,
  limit: number,
  blockedOnly: boolean
): Promise<AuditLogResponse> {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    blocked_only: blockedOnly ? "true" : "false",
  });
  return apiRequest<AuditLogResponse>(`/admin/audit-log?${params.toString()}`, { token });
}

export function getDataSources(token: string): Promise<DataSourceItem[]> {
  return apiRequest<DataSourceItem[]>("/admin/data-sources", { token });
}

export function getLatencyFlag(latencyMs: number): "suspicious" | "normal" | "high" {
  if (latencyMs < 500) {
    return "suspicious";
  }
  if (latencyMs <= 2000) {
    return "normal";
  }
  return "high";
}
