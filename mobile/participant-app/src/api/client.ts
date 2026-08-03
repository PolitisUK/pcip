import { env } from "../config/env";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  accessToken?: string;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
};

type ApiErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string | null;
  };
  retry_after_seconds?: number;
};

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null;
  readonly kind: "http" | "network" | "timeout";

  constructor(args: {
    status: number;
    message: string;
    code?: string | null;
    requestId?: string | null;
    retryAfterSeconds?: number | null;
    kind?: "http" | "network" | "timeout";
  }) {
    super(args.message);
    this.name = "ApiRequestError";
    this.status = args.status;
    this.code = args.code || null;
    this.requestId = args.requestId || null;
    this.retryAfterSeconds = args.retryAfterSeconds ?? null;
    this.kind = args.kind || "http";
  }
}

function parseRetryAfter(headers: Headers): number | null {
  const retryAfterHeader = headers.get("Retry-After");
  if (!retryAfterHeader) {
    return null;
  }

  const numeric = Number.parseInt(retryAfterHeader, 10);
  if (Number.isFinite(numeric) && numeric > 0) {
    return numeric;
  }
  return null;
}

async function parseApiErrorEnvelope(response: Response): Promise<ApiErrorEnvelope | null> {
  try {
    return (await response.json()) as ApiErrorEnvelope;
  } catch {
    return null;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method || "GET";
  const timeoutMs = options.timeoutMs ?? 12000;

  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  options.signal?.addEventListener("abort", onAbort);

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers || {}),
  };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }

  try {
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });

    if (!response.ok) {
      const payload = await parseApiErrorEnvelope(response);
      throw new ApiRequestError({
        status: response.status,
        code: payload?.error?.code || null,
        requestId: payload?.error?.request_id || null,
        retryAfterSeconds: payload?.retry_after_seconds ?? parseRetryAfter(response.headers),
        message: payload?.error?.message || `Request failed with status ${response.status}`,
      });
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error;
    }

    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiRequestError({
        status: 0,
        code: null,
        requestId: null,
        retryAfterSeconds: null,
        kind: "timeout",
        message: "Request timed out",
      });
    }

    throw new ApiRequestError({
      status: 0,
      code: null,
      requestId: null,
      retryAfterSeconds: null,
      kind: "network",
      message: "Network request failed",
    });
  } finally {
    clearTimeout(timeoutHandle);
    options.signal?.removeEventListener("abort", onAbort);
  }
}
