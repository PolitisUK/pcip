import type {
  components,
} from "./generated/participant-api-types";
import { apiRequest } from "./client";

type SessionExchangeRequest = components["schemas"]["SessionExchangeRequest"];
type SessionExchangeResponse = components["schemas"]["SessionExchangeResponse"];
type ParticipantSessionResponse = components["schemas"]["ParticipantSessionResponse"];
type LogoutResponse = components["schemas"]["LogoutResponse"];
type StudyListResponse = components["schemas"]["StudyListResponse"];
type ActivityListResponse = components["schemas"]["ActivityListResponse"];
type ActivityDetailResponse = components["schemas"]["ActivityDetailResponse"];
type DraftResponseRequest = components["schemas"]["DraftResponseRequest"];
type DraftResponseResult = components["schemas"]["DraftResponseResult"];
type SubmitResponseRequest = components["schemas"]["SubmitResponseRequest"];
type SubmittedResponseResult = components["schemas"]["SubmittedResponseResult"];

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

export async function getParticipantStudies(accessToken: string, options?: RequestOptions): Promise<StudyListResponse> {
  return apiRequest<StudyListResponse>("/api/v1/participant/studies", {
    method: "GET",
    accessToken,
    signal: options?.signal,
  });
}

export async function getParticipantActivities(
  accessToken: string,
  studyId?: number,
  options?: RequestOptions,
): Promise<ActivityListResponse> {
  const query = typeof studyId === "number" ? `?study_id=${encodeURIComponent(String(studyId))}` : "";

  return apiRequest<ActivityListResponse>(`/api/v1/participant/activities${query}`, {
    method: "GET",
    accessToken,
    signal: options?.signal,
  });
}

export async function getParticipantActivityDetail(
  accessToken: string,
  activityId: number,
  options?: RequestOptions,
): Promise<ActivityDetailResponse> {
  return apiRequest<ActivityDetailResponse>(`/api/v1/participant/activities/${activityId}`, {
    method: "GET",
    accessToken,
    signal: options?.signal,
  });
}

export async function saveParticipantActivityDraft(
  accessToken: string,
  activityId: number,
  payload: DraftResponseRequest,
  options?: RequestOptions,
): Promise<DraftResponseResult> {
  return apiRequest<DraftResponseResult>(`/api/v1/participant/activities/${activityId}/draft`, {
    method: "PUT",
    accessToken,
    body: payload,
    headers: withIdempotencyHeader(options),
    signal: options?.signal,
  });
}

export async function submitParticipantActivityResponse(
  accessToken: string,
  activityId: number,
  payload: SubmitResponseRequest,
  options?: RequestOptions,
): Promise<SubmittedResponseResult> {
  return apiRequest<SubmittedResponseResult>(`/api/v1/participant/activities/${activityId}/submit`, {
    method: "POST",
    accessToken,
    body: payload,
    headers: withIdempotencyHeader(options),
    signal: options?.signal,
  });
}

export type {
  SessionExchangeRequest,
  SessionExchangeResponse,
  ParticipantSessionResponse,
  LogoutResponse,
  StudyListResponse,
  ActivityListResponse,
  ActivityDetailResponse,
  DraftResponseRequest,
  DraftResponseResult,
  SubmitResponseRequest,
  SubmittedResponseResult,
};
