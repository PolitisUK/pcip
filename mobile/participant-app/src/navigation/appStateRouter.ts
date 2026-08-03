import type { AuthState } from "../auth/types";
import type { RootStackParamList } from "./types";

export function routeNameForAuthState(state: AuthState): keyof RootStackParamList {
  switch (state.status) {
    case "initialising":
    case "processing_invitation":
      return "ProcessingInvitation";
    case "signed_out":
      return "SignedOut";
    case "consent_required":
      return "ConsentRequired";
    case "authenticated":
      return "AuthenticatedHome";
    case "recoverable_error":
      return "RecoverableError";
    case "terminal_error":
      return "TerminalError";
    default:
      return "SignedOut";
  }
}
