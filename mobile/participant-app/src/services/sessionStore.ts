import * as SecureStore from "expo-secure-store";

const ACCESS_TOKEN_KEY = "participant_api_access_token";
const EXPIRES_AT_KEY = "participant_api_expires_at";

type SessionMaterial = {
  accessToken: string;
  expiresAt: string;
};

export async function saveSessionMaterial(session: SessionMaterial): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, session.accessToken);
  await SecureStore.setItemAsync(EXPIRES_AT_KEY, session.expiresAt);
}

export async function loadSessionMaterial(): Promise<SessionMaterial | null> {
  const [accessToken, expiresAt] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.getItemAsync(EXPIRES_AT_KEY),
  ]);

  if (!accessToken || !expiresAt) {
    return null;
  }

  return {
    accessToken,
    expiresAt,
  };
}

export async function clearSessionMaterial(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(EXPIRES_AT_KEY),
  ]);
}
