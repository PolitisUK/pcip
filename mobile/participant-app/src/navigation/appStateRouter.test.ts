import type { AuthState } from "../auth/types";
import { routeNameForAuthState } from "./appStateRouter";

describe("routeNameForAuthState", () => {
  it("routes signed out state", () => {
    expect(routeNameForAuthState({ status: "signed_out" })).toBe("SignedOut");
  });

  it("routes processing invitation state", () => {
    expect(routeNameForAuthState({ status: "processing_invitation" })).toBe("ProcessingInvitation");
  });

  it("routes authenticated state", () => {
    const state: AuthState = {
      status: "authenticated",
      participantDisplayName: "Alex",
    };
    expect(routeNameForAuthState(state)).toBe("AuthenticatedHome");
  });

  it("routes consent required state", () => {
    const state: AuthState = {
      status: "consent_required",
      participantDisplayName: "Alex",
      studyId: 1,
    };
    expect(routeNameForAuthState(state)).toBe("ConsentRequired");
  });

  it("routes error states", () => {
    expect(routeNameForAuthState({ status: "recoverable_error", reason: "network" })).toBe("RecoverableError");
    expect(routeNameForAuthState({ status: "terminal_error", reason: "forbidden" })).toBe("TerminalError");
  });
});
