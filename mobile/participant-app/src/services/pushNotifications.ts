import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";

const PREFS_KEY = "participant_push_notification_prefs";

export type NotificationPreferences = {
  enabled: boolean;
  expoPushToken?: string;
  updatedAt: string;
};

export type PushRegistrationResult =
  | { status: "enabled"; token: string }
  | { status: "denied"; message: string }
  | { status: "unsupported"; message: string }
  | { status: "error"; message: string };

function nowIso(): string {
  return new Date().toISOString();
}

function parsePreferences(raw: string | null): NotificationPreferences | null {
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<NotificationPreferences>;
    if (typeof parsed.enabled !== "boolean" || typeof parsed.updatedAt !== "string") {
      return null;
    }
    return {
      enabled: parsed.enabled,
      expoPushToken: typeof parsed.expoPushToken === "string" ? parsed.expoPushToken : undefined,
      updatedAt: parsed.updatedAt,
    };
  } catch {
    return null;
  }
}

export async function loadNotificationPreferences(): Promise<NotificationPreferences | null> {
  const raw = await SecureStore.getItemAsync(PREFS_KEY);
  return parsePreferences(raw);
}

export async function saveNotificationPreferences(preferences: NotificationPreferences): Promise<void> {
  await SecureStore.setItemAsync(PREFS_KEY, JSON.stringify(preferences));
}

export async function disablePushNotificationsLocally(): Promise<void> {
  await saveNotificationPreferences({
    enabled: false,
    updatedAt: nowIso(),
  });
}

function resolveProjectId(): string | undefined {
  const fromExtra = (Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined)?.eas?.projectId;
  const fromEnv = process.env.EXPO_PUBLIC_EAS_PROJECT_ID;
  if (typeof fromExtra === "string" && fromExtra.trim()) {
    return fromExtra.trim();
  }
  if (typeof fromEnv === "string" && fromEnv.trim()) {
    return fromEnv.trim();
  }
  return undefined;
}

export async function registerForPushNotifications(): Promise<PushRegistrationResult> {
  if (!Device.isDevice) {
    return {
      status: "unsupported",
      message: "Push notifications require a physical device.",
    };
  }

  const existing = await Notifications.getPermissionsAsync();
  let finalStatus = existing.status;
  if (finalStatus !== "granted") {
    const requested = await Notifications.requestPermissionsAsync();
    finalStatus = requested.status;
  }

  if (finalStatus !== "granted") {
    await disablePushNotificationsLocally();
    return {
      status: "denied",
      message: "Notification permission was not granted.",
    };
  }

  try {
    const projectId = resolveProjectId();
    const tokenResponse = projectId
      ? await Notifications.getExpoPushTokenAsync({ projectId })
      : await Notifications.getExpoPushTokenAsync();

    await saveNotificationPreferences({
      enabled: true,
      expoPushToken: tokenResponse.data,
      updatedAt: nowIso(),
    });

    return {
      status: "enabled",
      token: tokenResponse.data,
    };
  } catch {
    return {
      status: "error",
      message: "Push setup failed. Please try again later.",
    };
  }
}
