type Env = {
  apiBaseUrl: string;
  deepLinkHost: string;
  deepLinkScheme: string;
};

function withDefault(value: string | undefined, fallback: string): string {
  const cleaned = (value || "").trim();
  return cleaned || fallback;
}

const API_BASE_URL = withDefault(process.env.EXPO_PUBLIC_API_BASE_URL, "https://staging.example.invalid");
const DEEP_LINK_HOST = withDefault(process.env.EXPO_PUBLIC_DEEP_LINK_HOST, "participant.staging.politis.co.uk");
const DEEP_LINK_SCHEME = withDefault(process.env.EXPO_PUBLIC_DEEP_LINK_SCHEME, "pcip-participant");

export const env: Env = {
  apiBaseUrl: API_BASE_URL.replace(/\/$/, ""),
  deepLinkHost: DEEP_LINK_HOST,
  deepLinkScheme: DEEP_LINK_SCHEME,
};
