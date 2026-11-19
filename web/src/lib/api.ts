export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** Do not broadcast a global unauthorized event (used by auth bootstrapping). */
  skipAuthEvent?: boolean;
}

function extractDetail(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const record = payload as Record<string, unknown>;
  const raw = record.detail ?? record.error ?? record.message;
  if (typeof raw === "string" && raw.trim()) return raw;
  if (Array.isArray(raw)) {
    const messages = raw
      .map((entry) => {
        if (entry && typeof entry === "object" && "msg" in entry) {
          return String((entry as Record<string, unknown>).msg);
        }
        return typeof entry === "string" ? entry : "";
      })
      .filter(Boolean);
    if (messages.length) return messages.join(" · ");
  }
  return fallback;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Requested-With": "XMLHttpRequest",
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: "same-origin",
      signal: options.signal,
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "The server could not be reached. Check that the engine is running.");
  }

  const contentType = response.headers.get("content-type") ?? "";
  let payload: unknown = null;
  if (contentType.includes("application/json")) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  } else {
    const text = await response.text();
    payload = text ? { detail: text } : null;
  }

  if (!response.ok) {
    if (response.status === 401 && !options.skipAuthEvent) {
      window.dispatchEvent(new Event("mm:unauthorized"));
    }
    throw new ApiError(
      response.status,
      extractDetail(payload, `Request failed with status ${response.status}`),
    );
  }

  return payload as T;
}

export function apiGet<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}) {
  return request<T>(path, { ...options, method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}) {
  return request<T>(path, { ...options, method: "POST", body });
}

export function apiPut<T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}) {
  return request<T>(path, { ...options, method: "PUT", body });
}

export function apiDelete<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}) {
  return request<T>(path, { ...options, method: "DELETE" });
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
