export type AuthState =
  | { status: "initialising" }
  | { status: "signed_out" }
  | { status: "processing_invitation" }
  | {
      status: "consent_required";
      participantDisplayName?: string;
      studyId?: number;
    }
  | {
      status: "authenticated";
      participantDisplayName?: string;
      participantId?: number;
      studyScope?: number[];
    }
  | {
      status: "recoverable_error";
      reason:
        | "invalid_invitation"
        | "expired_invitation"
        | "already_used_invitation"
        | "network"
        | "rate_limited"
        | "temporary_service"
        | "secure_storage";
    }
  | {
      status: "terminal_error";
      reason: "revoked_session" | "invalid_session" | "forbidden";
    };
