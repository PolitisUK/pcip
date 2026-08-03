import type {
  components,
} from "./generated/participant-api-types";
import { env } from "../config/env";
import { ApiRequestError, apiRequest } from "./client";

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
type EvidenceUploadResponse = components["schemas"]["EvidenceUploadResponse"];
type EvidenceStatusResponse = components["schemas"]["EvidenceStatusResponse"];
type EvidenceMetadata = components["schemas"]["EvidenceMetadata"];
type MessageListResponse = components["schemas"]["MessageListResponse"];
type CreateMessageRequest = components["schemas"]["CreateMessageRequest"];
type CreateMessageResponse = components["schemas"]["CreateMessageResponse"];
type WithdrawalRequest = components["schemas"]["WithdrawalRequest"];
type DeletionRequest = components["schemas"]["DeletionRequest"];
type PrivacyRequestAcknowledgement = components["schemas"]["PrivacyRequestAcknowledgement"];

type RequestOptions = {
  signal?: AbortSignal;
  idempotencyKey?: string;
  timeoutMs?: number;
};

type UploadEvidenceInput = {
  localUri: string;
  filename: string;
  contentType: string;
  note?: string;
  onProgress?: (progressRatio: number) => void;
};

type ApiErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string | null;
  };
  retry_after_seconds?: number;
};

type JsonObject = Record<string, unknown>;

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

export async function uploadParticipantActivityEvidence(
  accessToken: string,
  activityId: number,
  input: UploadEvidenceInput,
  options?: RequestOptions,
): Promise<EvidenceUploadResponse> {
  return new Promise<EvidenceUploadResponse>((resolve, reject) => {
    const formData = new FormData();
    formData.append("activity_id", String(activityId));
    if (input.note) {
      formData.append("note", input.note);
    }
    formData.append("file", {
      uri: input.localUri,
      name: input.filename,
      type: input.contentType,
    } as unknown as Blob);

    const xhr = new XMLHttpRequest();
    const timeoutMs = options?.timeoutMs ?? 30000;
    let timedOut = false;
    const timeoutHandle = setTimeout(() => {
      timedOut = true;
      xhr.abort();
    }, timeoutMs);

    const onAbort = () => {
      xhr.abort();
    };
    options?.signal?.addEventListener("abort", onAbort);

    const finish = () => {
      clearTimeout(timeoutHandle);
      options?.signal?.removeEventListener("abort", onAbort);
    };

    xhr.upload.onprogress = (event) => {
      if (!input.onProgress || !event.lengthComputable || event.total <= 0) {
        return;
      }
      const ratio = Math.max(0, Math.min(1, event.loaded / event.total));
      input.onProgress(ratio);
    };

    xhr.onerror = () => {
      finish();
      reject(
        new ApiRequestError({
          status: 0,
          code: null,
          requestId: null,
          retryAfterSeconds: null,
          kind: "network",
          message: "Network request failed",
        }),
      );
    };

    xhr.onabort = () => {
      finish();
      reject(
        new ApiRequestError({
          status: 0,
          code: null,
          requestId: null,
          retryAfterSeconds: null,
          kind: timedOut ? "timeout" : "network",
          message: timedOut ? "Request timed out" : "Request was cancelled",
        }),
      );
    };

    xhr.onload = () => {
      finish();

      const raw = typeof xhr.responseText === "string" ? xhr.responseText : "";
      const payload = parseJsonObject(raw);
      const envelope = parseApiErrorEnvelope(payload);
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(
          new ApiRequestError({
            status: xhr.status,
            code: envelope?.error?.code || null,
            requestId: envelope?.error?.request_id || null,
            retryAfterSeconds: envelope?.retry_after_seconds ?? null,
            message: envelope?.error?.message || `Request failed with status ${xhr.status}`,
          }),
        );
        return;
      }

      if (!payload || typeof payload !== "object" || !("evidence" in payload)) {
        reject(
          new ApiRequestError({
            status: xhr.status || 0,
            code: null,
            requestId: null,
            retryAfterSeconds: null,
            kind: "network",
            message: "Unexpected upload response.",
          }),
        );
        return;
      }

      resolve(payload as EvidenceUploadResponse);
    };

    xhr.open("POST", `${env.apiBaseUrl}/api/v1/participant/activities/${activityId}/evidence-uploads`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
    if (options?.idempotencyKey) {
      xhr.setRequestHeader("Idempotency-Key", options.idempotencyKey);
    }
    xhr.send(formData);
  });
}

export async function getParticipantEvidenceStatus(
  accessToken: string,
  evidenceId: number,
  options?: RequestOptions,
): Promise<EvidenceStatusResponse> {
  return apiRequest<EvidenceStatusResponse>(`/api/v1/participant/evidence/${evidenceId}/status`, {
    method: "GET",
    accessToken,
    signal: options?.signal,
  });
}

export async function getParticipantMessages(
  accessToken: string,
  options?: RequestOptions,
): Promise<MessageListResponse> {
  return apiRequest<MessageListResponse>("/api/v1/participant/messages", {
    method: "GET",
    accessToken,
    signal: options?.signal,
  });
}

export async function createParticipantMessage(
  accessToken: string,
  payload: CreateMessageRequest,
  options?: RequestOptions,
): Promise<CreateMessageResponse> {
  return apiRequest<CreateMessageResponse>("/api/v1/participant/messages", {
    method: "POST",
    accessToken,
    body: payload,
    headers: withIdempotencyHeader(options),
    signal: options?.signal,
  });
}

export async function requestParticipantWithdrawal(
  accessToken: string,
  payload: WithdrawalRequest,
  options?: RequestOptions,
): Promise<PrivacyRequestAcknowledgement> {
  return apiRequest<PrivacyRequestAcknowledgement>("/api/v1/participant/privacy/withdrawal-requests", {
    method: "POST",
    accessToken,
    body: payload,
    headers: withIdempotencyHeader(options),
    signal: options?.signal,
  });
}

export async function requestParticipantDeletion(
  accessToken: string,
  payload: DeletionRequest,
  options?: RequestOptions,
): Promise<PrivacyRequestAcknowledgement> {
  return apiRequest<PrivacyRequestAcknowledgement>("/api/v1/participant/privacy/deletion-requests", {
    method: "POST",
    accessToken,
    body: payload,
    headers: withIdempotencyHeader(options),
    signal: options?.signal,
  });
}

function parseJsonObject(raw: string): JsonObject | null {
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed as JsonObject;
  } catch {
    return null;
  }
}

function parseApiErrorEnvelope(payload: JsonObject | null): ApiErrorEnvelope | null {
  if (!payload) {
    return null;
  }

  const rawError = payload.error;
  const error = rawError && typeof rawError === "object"
    ? {
        code: typeof (rawError as JsonObject).code === "string" ? (rawError as JsonObject).code as string : undefined,
        message: typeof (rawError as JsonObject).message === "string" ? (rawError as JsonObject).message as string : undefined,
        request_id: typeof (rawError as JsonObject).request_id === "string" ? (rawError as JsonObject).request_id as string : null,
      }
    : undefined;

  return {
    error,
    retry_after_seconds: typeof payload.retry_after_seconds === "number" ? payload.retry_after_seconds : undefined,
  };
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
  EvidenceMetadata,
  EvidenceUploadResponse,
  EvidenceStatusResponse,
  UploadEvidenceInput,
  MessageListResponse,
  CreateMessageRequest,
  CreateMessageResponse,
  WithdrawalRequest,
  DeletionRequest,
  PrivacyRequestAcknowledgement,
};
