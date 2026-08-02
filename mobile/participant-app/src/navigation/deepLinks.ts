import type { LinkingOptions } from "@react-navigation/native";

import { env } from "../config/env";
import type { RootStackParamList } from "./types";

export function parseInvitationTokenFromUrl(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }

  const scheme = parsed.protocol.replace(/:$/, "").toLowerCase();
  const host = parsed.hostname.toLowerCase();
  const path = parsed.pathname.replace(/^\/+/, "").toLowerCase();

  const httpsAllowed = scheme === "https" && host === env.deepLinkHost.toLowerCase() && path === "join-study";
  const schemeAllowed = scheme === env.deepLinkScheme.toLowerCase() && (path === "join-study" || host === "join-study");

  if (!httpsAllowed && !schemeAllowed) {
    return null;
  }

  const token = parsed.searchParams.get("token");
  if (typeof token !== "string") {
    return null;
  }

  const trimmed = token.trim();
  return trimmed ? trimmed : null;
}

export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: [
    `${env.deepLinkScheme}://`,
    `https://${env.deepLinkHost}`,
  ],
  config: {
    screens: {
      Home: "",
      Invitation: {
        path: "join-study",
        parse: {
          token: (value: string) => value,
        },
      },
    },
  },
};
