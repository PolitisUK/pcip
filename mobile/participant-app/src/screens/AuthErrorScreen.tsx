import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AuthState } from "../auth/types";

type RecoverableReason = Extract<AuthState, { status: "recoverable_error" }>["reason"];
type TerminalReason = Extract<AuthState, { status: "terminal_error" }>["reason"];

type AuthErrorScreenProps = {
  state: Extract<AuthState, { status: "recoverable_error" | "terminal_error" }>;
  onRetry: () => void;
  onSignOut: () => void;
};

function mapRecoverableCopy(reason: RecoverableReason): { title: string; body: string } {
  switch (reason) {
    case "invalid_invitation":
      return {
        title: "Invitation link not recognised",
        body: "This invitation link is invalid or expired. Open a valid Citizen Centric invitation from your research team.",
      };
    case "expired_invitation":
      return {
        title: "Invitation link expired",
        body: "This invitation has expired or is no longer available. Ask your research team for a new Citizen Centric invitation.",
      };
    case "already_used_invitation":
      return {
        title: "Invitation already used",
        body: "This invitation is already active. Try restoring your saved Citizen Centric session or contact your research team.",
      };
    case "network":
      return {
        title: "Connection problem",
        body: "We could not reach Citizen Centric securely. Check your connection and try again.",
      };
    case "rate_limited":
      return {
        title: "Please try again shortly",
        body: "Too many attempts were made recently. Wait a moment, then retry your Citizen Centric invitation.",
      };
    case "secure_storage":
      return {
        title: "Device storage unavailable",
        body: "Citizen Centric could not securely access local sign-in storage. Try again or contact your research team.",
      };
    case "temporary_service":
    default:
      return {
        title: "Temporary service problem",
        body: "Citizen Centric is temporarily unavailable. Please try again shortly.",
      };
  }
}

function mapTerminalCopy(reason: TerminalReason): { title: string; body: string } {
  switch (reason) {
    case "revoked_session":
      return {
        title: "Session ended",
        body: "Your Citizen Centric session is no longer active. Open your invitation link to sign in again.",
      };
    case "forbidden":
      return {
        title: "Access unavailable",
        body: "This session is no longer authorised for Citizen Centric participant access. Contact your research team.",
      };
    case "invalid_session":
    default:
      return {
        title: "Session invalid",
        body: "Your saved Citizen Centric session is invalid. Sign in again with your invitation link.",
      };
  }
}

export function AuthErrorScreen({ state, onRetry, onSignOut }: AuthErrorScreenProps) {
  const copy = state.status === "recoverable_error" ? mapRecoverableCopy(state.reason) : mapTerminalCopy(state.reason);

  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        {copy.title}
      </Text>
      <Text style={styles.body}>{copy.body}</Text>

      <View style={styles.row}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Try again"
          onPress={onRetry}
          style={styles.primaryButton}
        >
          <Text style={styles.primaryButtonText}>Try again</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Open a different invitation"
          onPress={onSignOut}
          style={styles.secondaryButton}
        >
          <Text style={styles.secondaryButtonText}>Open a different invitation</Text>
        </Pressable>
      </View>
      <Text style={styles.hint}>If this keeps happening, contact the research team.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#f7faf8",
    paddingHorizontal: 24,
    paddingVertical: 28,
    gap: 14,
  },
  title: {
    color: "#0c2f24",
    fontSize: 24,
    fontWeight: "700",
  },
  body: {
    color: "#25433a",
    fontSize: 16,
    lineHeight: 22,
  },
  row: {
    marginTop: 8,
    gap: 10,
  },
  primaryButton: {
    borderRadius: 12,
    backgroundColor: "#00573d",
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  primaryButtonText: {
    color: "#ffffff",
    fontSize: 15,
    fontWeight: "600",
    textAlign: "center",
  },
  secondaryButton: {
    borderRadius: 12,
    backgroundColor: "#dfeee8",
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  secondaryButtonText: {
    color: "#0d3a2d",
    fontSize: 15,
    fontWeight: "600",
    textAlign: "center",
  },
  hint: {
    marginTop: 6,
    color: "#35574c",
    fontSize: 14,
  },
});
