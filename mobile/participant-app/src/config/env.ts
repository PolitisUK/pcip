type Env = {
  apiBaseUrl: string;
  deepLinkHost: string;
  deepLinkScheme: string;
  privacyUrl: string;
  termsUrl: string;
  supportUrl: string;
};

function withDefault(value: string | undefined, fallback: string): string {
  const cleaned = (value || "").trim();
  return cleaned || fallback;
}

const API_BASE_URL = withDefault(process.env.EXPO_PUBLIC_API_BASE_URL, "https://staging.example.invalid");
const DEEP_LINK_HOST = withDefault(process.env.EXPO_PUBLIC_DEEP_LINK_HOST, "participant.staging.politis.co.uk");
const DEEP_LINK_SCHEME = withDefault(process.env.EXPO_PUBLIC_DEEP_LINK_SCHEME, "pcip-participant");
const PRIVACY_URL = withDefault(process.env.EXPO_PUBLIC_PRIVACY_URL, "https://citizencentric.co.uk/privacy");
const TERMS_URL = withDefault(process.env.EXPO_PUBLIC_TERMS_URL, "https://citizencentric.co.uk/terms");
const SUPPORT_URL = withDefault(process.env.EXPO_PUBLIC_SUPPORT_URL, "https://citizencentric.co.uk/support");

export const env: Env = {
  apiBaseUrl: API_BASE_URL.replace(/\/$/, ""),
  deepLinkHost: DEEP_LINK_HOST,
  deepLinkScheme: DEEP_LINK_SCHEME,
  privacyUrl: PRIVACY_URL,
  termsUrl: TERMS_URL,
  supportUrl: SUPPORT_URL,
};
