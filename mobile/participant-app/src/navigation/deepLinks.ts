import type { LinkingOptions } from "@react-navigation/native";

import { env } from "../config/env";
import type { RootStackParamList } from "./types";

export type InvitationLinkParseResult =
  | { kind: "token"; token: string }
  | { kind: "invalid_invitation" }
  | { kind: "ignore" };

export function parseInvitationLink(url: string): InvitationLinkParseResult {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return { kind: "ignore" };
  }

  const scheme = parsed.protocol.replace(/:$/, "").toLowerCase();
  const host = parsed.hostname.toLowerCase();
  const path = parsed.pathname.replace(/^\/+/, "").toLowerCase();

  const httpsAllowed = scheme === "https" && host === env.deepLinkHost.toLowerCase() && path === "join-study";
  const schemeAllowed = scheme === env.deepLinkScheme.toLowerCase() && (path === "join-study" || host === "join-study");

  if (!httpsAllowed && !schemeAllowed) {
    return { kind: "ignore" };
  }

  const token = parsed.searchParams.get("token");
  if (typeof token !== "string") {
    return { kind: "invalid_invitation" };
  }

  let decoded = token;
  try {
    decoded = decodeURIComponent(token);
  } catch {
    decoded = token;
  }

  const trimmed = decoded.trim();
  if (!trimmed) {
    return { kind: "invalid_invitation" };
  }

  return { kind: "token", token: trimmed };
}

export function parseInvitationTokenFromUrl(url: string): string | null {
  const result = parseInvitationLink(url);
  return result.kind === "token" ? result.token : null;
}

export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: [
    `${env.deepLinkScheme}://`,
    `https://${env.deepLinkHost}`,
  ],
};
