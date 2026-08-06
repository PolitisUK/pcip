process.env.EXPO_PUBLIC_API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || "https://participant.staging.politis.co.uk";
process.env.EXPO_PUBLIC_DEEP_LINK_HOST = process.env.EXPO_PUBLIC_DEEP_LINK_HOST || "participant.staging.politis.co.uk";
process.env.EXPO_PUBLIC_DEEP_LINK_SCHEME = process.env.EXPO_PUBLIC_DEEP_LINK_SCHEME || "pcip-participant";

if (typeof (globalThis as { window?: unknown }).window === "undefined") {
	(globalThis as { window?: unknown }).window = globalThis;
}

const maybeWindow = (globalThis as { window: { dispatchEvent?: (event: unknown) => boolean } }).window;
if (typeof maybeWindow.dispatchEvent !== "function") {
	maybeWindow.dispatchEvent = () => false;
}
