import * as SecureStore from "expo-secure-store";

const ACCESS_TOKEN_KEY = "participant_api_access_token";
const EXPIRES_AT_KEY = "participant_api_expires_at";
const PARTICIPANT_ID_KEY = "participant_api_participant_id";
const PARTICIPANT_NAME_KEY = "participant_api_participant_display_name";
const CONSENT_STATUS_KEY = "participant_api_consent_status";
const STUDY_SCOPE_KEY = "participant_api_study_scope";

export type SessionMaterial = {
  accessToken: string;
  expiresAt: string;
  participantId?: number;
  participantDisplayName?: string;
  consentStatus?: "pending" | "granted" | "declined" | "withdrawn";
  studyScope?: number[];
};

function safeJsonParse<T>(value: string | null): T | null {
  if (!value) {
    return null;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

function isIsoDateTime(value: string): boolean {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed);
}

function normalizeSession(raw: SessionMaterial): SessionMaterial | null {
  const accessToken = raw.accessToken?.trim();
  const expiresAt = raw.expiresAt?.trim();

  if (!accessToken || !expiresAt || !isIsoDateTime(expiresAt)) {
    return null;
  }

  return {
    accessToken,
    expiresAt,
    participantId: typeof raw.participantId === "number" ? raw.participantId : undefined,
    participantDisplayName: typeof raw.participantDisplayName === "string" ? raw.participantDisplayName : undefined,
    consentStatus: raw.consentStatus,
    studyScope: Array.isArray(raw.studyScope)
      ? raw.studyScope.filter((value): value is number => typeof value === "number")
      : undefined,
  };
}

export async function saveSessionMaterial(session: SessionMaterial): Promise<void> {
  const normalized = normalizeSession(session);
  if (!normalized) {
    throw new Error("Invalid session material");
  }

  await Promise.all([
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, normalized.accessToken),
    SecureStore.setItemAsync(EXPIRES_AT_KEY, normalized.expiresAt),
    SecureStore.setItemAsync(PARTICIPANT_ID_KEY, normalized.participantId ? String(normalized.participantId) : ""),
    SecureStore.setItemAsync(PARTICIPANT_NAME_KEY, normalized.participantDisplayName || ""),
    SecureStore.setItemAsync(CONSENT_STATUS_KEY, normalized.consentStatus || ""),
    SecureStore.setItemAsync(STUDY_SCOPE_KEY, JSON.stringify(normalized.studyScope || [])),
  ]);
}

export async function loadSessionMaterial(): Promise<SessionMaterial | null> {
  const [accessToken, expiresAt, participantIdRaw, participantDisplayName, consentStatusRaw, studyScopeRaw] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.getItemAsync(EXPIRES_AT_KEY),
    SecureStore.getItemAsync(PARTICIPANT_ID_KEY),
    SecureStore.getItemAsync(PARTICIPANT_NAME_KEY),
    SecureStore.getItemAsync(CONSENT_STATUS_KEY),
    SecureStore.getItemAsync(STUDY_SCOPE_KEY),
  ]);

  if (!accessToken || !expiresAt) {
    return null;
  }

  const participantId = participantIdRaw ? Number.parseInt(participantIdRaw, 10) : undefined;
  const consentStatus = consentStatusRaw || undefined;
  const studyScope = safeJsonParse<number[]>(studyScopeRaw) || undefined;

  const normalized = normalizeSession({
    accessToken,
    expiresAt,
    participantId,
    participantDisplayName: participantDisplayName || undefined,
    consentStatus: consentStatus as SessionMaterial["consentStatus"],
    studyScope,
  });

  if (!normalized) {
    await clearSessionMaterial();
    return null;
  }

  return normalized;
}

export async function clearSessionMaterial(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(EXPIRES_AT_KEY),
    SecureStore.deleteItemAsync(PARTICIPANT_ID_KEY),
    SecureStore.deleteItemAsync(PARTICIPANT_NAME_KEY),
    SecureStore.deleteItemAsync(CONSENT_STATUS_KEY),
    SecureStore.deleteItemAsync(STUDY_SCOPE_KEY),
  ]);
}
