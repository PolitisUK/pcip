import type {
  components,
} from "./generated/participant-api-types";
import { apiRequest } from "./client";

type SessionExchangeRequest = components["schemas"]["SessionExchangeRequest"];
type SessionExchangeResponse = components["schemas"]["SessionExchangeResponse"];
type ParticipantSessionResponse = components["schemas"]["ParticipantSessionResponse"];
type LogoutResponse = components["schemas"]["LogoutResponse"];

type RequestOptions = {
  signal?: AbortSignal;
  idempotencyKey?: string;
};

function withIdempotencyHeader(options?: RequestOptions): Record<string, string> | undefined {
  if (!options?.idempotencyKey) {
    return undefined;
  }

  return {
    "Idempotency-Key": options.idempotencyKey,
  };
}

export async function exchangeSession(payload: SessionExchangeRequest, options?: RequestOptions): Promise<SessionExchangeResponse> {
  return apiRequest<SessionExchangeResponse>("/api/v1/participant/session/exchange", {
    method: "POST",
    body: payload,
    headers: withIdempotencyHeader(options),
    signal: options?.signal,
  });
}

export async function getCurrentSession(accessToken: string, options?: RequestOptions): Promise<ParticipantSessionResponse> {
  return apiRequest<ParticipantSessionResponse>("/api/v1/participant/session", {
    method: "GET",
    accessToken,
    signal: options?.signal,
  });
}

export async function revokeCurrentSession(accessToken: string, options?: RequestOptions): Promise<LogoutResponse> {
  return apiRequest<LogoutResponse>("/api/v1/participant/session", {
    method: "DELETE",
    accessToken,
    headers: withIdempotencyHeader(options),
    signal: options?.signal,
  });
}

export type {
  SessionExchangeRequest,
  SessionExchangeResponse,
  ParticipantSessionResponse,
  LogoutResponse,
};
