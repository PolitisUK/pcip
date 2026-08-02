import type {
  components,
} from "./generated/participant-api-types";
import { apiRequest } from "./client";

type SessionExchangeRequest = components["schemas"]["SessionExchangeRequest"];
type SessionExchangeResponse = components["schemas"]["SessionExchangeResponse"];
type ParticipantSessionResponse = components["schemas"]["ParticipantSessionResponse"];
type LogoutResponse = components["schemas"]["LogoutResponse"];

export async function exchangeSession(payload: SessionExchangeRequest): Promise<SessionExchangeResponse> {
  return apiRequest<SessionExchangeResponse>("/api/v1/participant/session/exchange", {
    method: "POST",
    body: payload,
  });
}

export async function getCurrentSession(accessToken: string): Promise<ParticipantSessionResponse> {
  return apiRequest<ParticipantSessionResponse>("/api/v1/participant/session", {
    method: "GET",
    accessToken,
  });
}

export async function revokeCurrentSession(accessToken: string): Promise<LogoutResponse> {
  return apiRequest<LogoutResponse>("/api/v1/participant/session", {
    method: "DELETE",
    accessToken,
  });
}
