import * as Linking from "expo-linking";

import { ApiRequestError } from "../api/client";
import {
  exchangeSession,
  getCurrentSession,
  revokeCurrentSession,
  type ParticipantSessionResponse,
  type SessionExchangeResponse,
} from "../api/participantApi";
import { parseInvitationLink } from "../navigation/deepLinks";
import {
  clearSessionMaterial,
  loadSessionMaterial,
  saveSessionMaterial,
  type SessionMaterial,
} from "../services/sessionStore";
import type { AuthState } from "./types";

type StateListener = (state: AuthState) => void;

export class AuthController {
  private state: AuthState = { status: "initialising" };
  private readonly listeners = new Set<StateListener>();
  private exchangeInFlight = false;
  private activeUrl: string | null = null;
  private lastInvitationUrl: string | null = null;
  private subscription: { remove: () => void } | null = null;
  private disposed = false;
  private operationVersion = 0;

  subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    listener(this.state);

    return () => {
      this.listeners.delete(listener);
    };
  }

  getState(): AuthState {
    return this.state;
  }

  private setState(state: AuthState): void {
    if (this.disposed) {
      return;
    }

    this.state = state;
    for (const listener of this.listeners) {
      listener(state);
    }
  }

  private beginOperation(): number {
    this.operationVersion += 1;
    return this.operationVersion;
  }

  private isCurrentOperation(operationVersion: number): boolean {
    return !this.disposed && this.operationVersion === operationVersion;
  }

  async initialise(): Promise<void> {
    this.attachLinkListener();

    try {
      const initialUrl = await Linking.getInitialURL();
      if (initialUrl) {
        const handled = await this.handleUrl(initialUrl);
        if (handled) {
          return;
        }
      }
    } catch {
      this.setState({ status: "recoverable_error", reason: "network" });
      return;
    }

    await this.restoreSession();
  }

  async restoreSession(): Promise<void> {
    const operationVersion = this.beginOperation();
    this.setState({ status: "initialising" });

    try {
      const stored = await loadSessionMaterial();
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }

      if (!stored) {
        this.setState({ status: "signed_out" });
        return;
      }

      if (Date.parse(stored.expiresAt) <= Date.now()) {
        await clearSessionMaterial();
        if (!this.isCurrentOperation(operationVersion)) {
          return;
        }
        this.setState({ status: "signed_out" });
        return;
      }

      const session = await getCurrentSession(stored.accessToken);
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }

      await saveSessionFromValidatedContext(stored.accessToken, session);
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }

      if (session.participant.consent_status !== "granted") {
        this.setState({
          status: "consent_required",
          participantDisplayName: session.participant.display_name,
          studyId: session.study_scope[0],
        });
        return;
      }

      this.setState({
        status: "authenticated",
        participantDisplayName: session.participant.display_name,
        participantId: session.participant.participant_id,
        studyScope: session.study_scope,
      });
    } catch (error) {
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }

      if (error instanceof ApiRequestError) {
        if (error.status === 401) {
          await clearSessionMaterial();
          if (!this.isCurrentOperation(operationVersion)) {
            return;
          }
          this.setState({ status: "terminal_error", reason: "revoked_session" });
          return;
        }

        if (error.status === 403) {
          await clearSessionMaterial();
          if (!this.isCurrentOperation(operationVersion)) {
            return;
          }
          this.setState({ status: "terminal_error", reason: "forbidden" });
          return;
        }

        if (error.kind === "network" || error.kind === "timeout") {
          this.setState({ status: "recoverable_error", reason: "network" });
          return;
        }
      }

      this.setState({ status: "recoverable_error", reason: "secure_storage" });
    }
  }

  async handleUrl(url: string): Promise<boolean> {
    if (this.exchangeInFlight) {
      return true;
    }
    if (this.activeUrl === url) {
      return true;
    }

    const parsedLink = parseInvitationLink(url);
    if (parsedLink.kind === "ignore") {
      return false;
    }

    if (parsedLink.kind === "invalid_invitation") {
      this.setState({ status: "recoverable_error", reason: "invalid_invitation" });
      return true;
    }

    const operationVersion = this.beginOperation();
    const token = parsedLink.token;
    this.lastInvitationUrl = url;
    this.exchangeInFlight = true;
    this.activeUrl = url;
    this.setState({ status: "processing_invitation" });

    try {
      const response = await exchangeSession(
        { invitation_token: token },
        { idempotencyKey: createIdempotencyKey() },
      );
      if (!this.isCurrentOperation(operationVersion)) {
        return true;
      }

      await saveSessionFromExchange(response);
      if (!this.isCurrentOperation(operationVersion)) {
        return true;
      }

      this.lastInvitationUrl = null;

      if (response.next_action === "consent_required" || response.participant.consent_status !== "granted") {
        this.setState({
          status: "consent_required",
          participantDisplayName: response.participant.display_name,
          studyId: response.invitation.study_id,
        });
        return true;
      }

      this.setState({
        status: "authenticated",
        participantDisplayName: response.participant.display_name,
        participantId: response.participant.participant_id,
        studyScope: [response.invitation.study_id],
      });
      return true;
    } catch (error) {
      if (!this.isCurrentOperation(operationVersion)) {
        return true;
      }
      this.setState(mapExchangeError(error));
      return true;
    } finally {
      if (this.isCurrentOperation(operationVersion)) {
        this.exchangeInFlight = false;
        this.activeUrl = null;
      }
    }
  }

  async retry(): Promise<void> {
    if (this.lastInvitationUrl && (this.state.status === "recoverable_error" || this.state.status === "processing_invitation")) {
      await this.handleUrl(this.lastInvitationUrl);
      return;
    }

    await this.restoreSession();
  }

  async refreshConsent(): Promise<void> {
    if (this.state.status !== "consent_required") {
      return;
    }

    await this.restoreSession();
  }

  async signOut(): Promise<void> {
    const operationVersion = this.beginOperation();
    this.lastInvitationUrl = null;
    this.exchangeInFlight = false;
    this.activeUrl = null;

    try {
      const current = await loadSessionMaterial();
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }
      if (current?.accessToken) {
        await revokeCurrentSession(current.accessToken, { idempotencyKey: createIdempotencyKey() });
      }
    } catch {
      // Best effort revocation; local secure clearing is authoritative for device state.
    } finally {
      await clearSessionMaterial();
      if (!this.isCurrentOperation(operationVersion)) {
        return;
      }
      this.setState({ status: "signed_out" });
    }
  }

  destroy(): void {
    this.disposed = true;
    this.operationVersion += 1;
    this.lastInvitationUrl = null;
    this.activeUrl = null;
    this.exchangeInFlight = false;
    this.subscription?.remove();
    this.subscription = null;
    this.listeners.clear();
  }

  private attachLinkListener(): void {
    if (this.subscription) {
      return;
    }

    const subscription = Linking.addEventListener("url", ({ url }) => {
      void this.handleUrl(url);
    });

    this.subscription = {
      remove: () => {
        subscription.remove();
      },
    };
  }
}

async function saveSessionFromValidatedContext(accessToken: string, session: ParticipantSessionResponse): Promise<void> {
  const material: SessionMaterial = {
    accessToken,
    expiresAt: session.session.expires_at,
    participantId: session.participant.participant_id,
    participantDisplayName: session.participant.display_name,
    consentStatus: session.participant.consent_status,
    studyScope: session.study_scope,
  };
  await saveSessionMaterial(material);
}

async function saveSessionFromExchange(response: SessionExchangeResponse): Promise<void> {
  const material: SessionMaterial = {
    accessToken: response.session.access_token,
    expiresAt: response.session.expires_at,
    participantId: response.participant.participant_id,
    participantDisplayName: response.participant.display_name,
    consentStatus: response.participant.consent_status,
    studyScope: [response.invitation.study_id],
  };

  await saveSessionMaterial(material);
}

function createIdempotencyKey(): string {
  return `mob-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function mapExchangeError(error: unknown): AuthState {
  if (!(error instanceof ApiRequestError)) {
    return { status: "recoverable_error", reason: "secure_storage" };
  }

  if (error instanceof ApiRequestError) {
    if (error.kind === "network" || error.kind === "timeout") {
      return { status: "recoverable_error", reason: "network" };
    }

    if (error.status === 400 || error.status === 422 || error.status === 404) {
      return { status: "recoverable_error", reason: "invalid_invitation" };
    }

    if (error.status === 401) {
      return { status: "recoverable_error", reason: "expired_invitation" };
    }

    if (error.status === 403) {
      return { status: "recoverable_error", reason: "expired_invitation" };
    }

    if (error.status === 409) {
      return { status: "recoverable_error", reason: "already_used_invitation" };
    }

    if (error.status === 429) {
      return { status: "recoverable_error", reason: "rate_limited" };
    }

    if (error.status >= 500) {
      return { status: "recoverable_error", reason: "temporary_service" };
    }
  }

  return { status: "recoverable_error", reason: "temporary_service" };
}
