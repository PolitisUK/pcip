import * as Linking from "expo-linking";

import { ApiRequestError } from "../api/client";
import {
  exchangeSession,
  getCurrentSession,
  revokeCurrentSession,
} from "../api/participantApi";
import {
  clearSessionMaterial,
  loadSessionMaterial,
  saveSessionMaterial,
} from "../services/sessionStore";
import { AuthController } from "./authController";

jest.mock("expo-linking", () => ({
  getInitialURL: jest.fn(),
  addEventListener: jest.fn(() => ({ remove: jest.fn() })),
}));

jest.mock("../api/participantApi", () => ({
  exchangeSession: jest.fn(),
  getCurrentSession: jest.fn(),
  revokeCurrentSession: jest.fn(),
}));

jest.mock("../services/sessionStore", () => ({
  saveSessionMaterial: jest.fn(),
  loadSessionMaterial: jest.fn(),
  clearSessionMaterial: jest.fn(),
}));

const mockedLinking = jest.mocked(Linking);
const mockedExchange = jest.mocked(exchangeSession);
const mockedGetCurrentSession = jest.mocked(getCurrentSession);
const mockedRevokeCurrentSession = jest.mocked(revokeCurrentSession);
const mockedSaveSessionMaterial = jest.mocked(saveSessionMaterial);
const mockedLoadSessionMaterial = jest.mocked(loadSessionMaterial);
const mockedClearSessionMaterial = jest.mocked(clearSessionMaterial);

function deferredPromise<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function createControllerWithStates() {
  const controller = new AuthController();
  const states: string[] = [];
  controller.subscribe((state) => states.push(state.status));
  return { controller, states };
}

describe("AuthController", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedLinking.getInitialURL.mockResolvedValue(null);
    mockedLoadSessionMaterial.mockResolvedValue(null);
  });

  it("restores signed out when no saved session exists", async () => {
    const { controller } = createControllerWithStates();

    await controller.initialise();

    expect(controller.getState()).toEqual({ status: "signed_out" });
  });

  it("restores authenticated state from a valid saved session", async () => {
    mockedLoadSessionMaterial.mockResolvedValue({
      accessToken: "token-123",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    mockedGetCurrentSession.mockResolvedValue({
      session: { expires_at: new Date(Date.now() + 60_000).toISOString(), revocable: true },
      participant: {
        display_name: "Alex",
        consent_status: "granted",
      },
      invitation: { study_id: 15, invitation_status: "accepted", expires_at: new Date(Date.now() + 60_000).toISOString(), accepted_at: new Date().toISOString(), requires_study_documents: false },
      next_action: "portal",
      study_scope: [15],
    });

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(controller.getState()).toEqual({
      status: "authenticated",
      participantDisplayName: "Alex",
      studyScope: [15],
    });
    expect(mockedSaveSessionMaterial).toHaveBeenCalled();
  });

  it("clears expired saved session", async () => {
    mockedLoadSessionMaterial.mockResolvedValue({
      accessToken: "token-123",
      expiresAt: new Date(Date.now() - 60_000).toISOString(),
    });

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(mockedClearSessionMaterial).toHaveBeenCalled();
    expect(controller.getState()).toEqual({ status: "signed_out" });
  });

  it("maps consent-required exchange response to consent state", async () => {
    mockedLinking.getInitialURL.mockResolvedValue(
      "https://participant.staging.politis.co.uk/join-study?token=abc123"
    );
    mockedExchange.mockResolvedValue({
      session: {
        access_token: "token-abc",
        token_type: "Bearer",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        revocable: true,
      },
      participant: {
        display_name: "Pat",
        consent_status: "granted",
      },
      invitation: {
        study_id: 22,
        invitation_status: "valid",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        accepted_at: null,
        requires_study_documents: true,
      },
      next_action: "consent_required",
    });

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(controller.getState()).toEqual({
      status: "consent_required",
      participantDisplayName: "Pat",
      studyId: 22,
    });
    expect(mockedSaveSessionMaterial).toHaveBeenCalled();
    expect(mockedSaveSessionMaterial.mock.calls[0]?.[0]).not.toHaveProperty("invitation_token");
  });

  it("maps invalid invitation error", async () => {
    mockedLinking.getInitialURL.mockResolvedValue(
      "https://participant.staging.politis.co.uk/join-study?token=bad"
    );
    mockedExchange.mockRejectedValue(
      new ApiRequestError({
        status: 404,
        message: "Not found",
      })
    );

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(controller.getState()).toEqual({ status: "recoverable_error", reason: "invalid_invitation" });
  });

  it("maps rate-limited exchange response", async () => {
    mockedLinking.getInitialURL.mockResolvedValue(
      "https://participant.staging.politis.co.uk/join-study?token=abc123"
    );
    mockedExchange.mockRejectedValue(
      new ApiRequestError({
        status: 429,
        message: "Too many requests",
      })
    );

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(controller.getState()).toEqual({ status: "recoverable_error", reason: "rate_limited" });
  });

  it("maps network failure as recoverable", async () => {
    mockedLinking.getInitialURL.mockResolvedValue(
      "https://participant.staging.politis.co.uk/join-study?token=abc123"
    );
    mockedExchange.mockRejectedValue(
      new ApiRequestError({
        status: 0,
        message: "Network request failed",
        kind: "network",
      })
    );

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(controller.getState()).toEqual({ status: "recoverable_error", reason: "network" });
  });

  it("maps secure storage failure during exchange as recoverable storage error", async () => {
    mockedLinking.getInitialURL.mockResolvedValue(
      "https://participant.staging.politis.co.uk/join-study?token=abc123"
    );
    mockedExchange.mockResolvedValue({
      session: {
        access_token: "token-abc",
        token_type: "Bearer",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        revocable: true,
      },
      participant: {
        display_name: "Pat",
        consent_status: "granted",
      },
      invitation: {
        study_id: 22,
        invitation_status: "valid",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        accepted_at: null,
        requires_study_documents: false,
      },
      next_action: "portal",
    });
    mockedSaveSessionMaterial.mockRejectedValue(new Error("Secure storage unavailable"));

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(controller.getState()).toEqual({ status: "recoverable_error", reason: "secure_storage" });
  });

  it("ignores unrelated links while signed out", async () => {
    const { controller } = createControllerWithStates();

    await controller.initialise();
    await controller.handleUrl("https://participant.staging.politis.co.uk/other-path?token=abc123");

    expect(mockedExchange).not.toHaveBeenCalled();
    expect(controller.getState()).toEqual({ status: "signed_out" });
  });

  it("prevents duplicate exchange while request is in progress", async () => {
    mockedExchange.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve({
        session: {
          access_token: "token-x",
          token_type: "Bearer",
          expires_at: new Date(Date.now() + 60_000).toISOString(),
          revocable: true,
        },
        participant: {
          display_name: "Casey",
          consent_status: "granted",
        },
        invitation: {
          study_id: 88,
          invitation_status: "valid",
          expires_at: new Date(Date.now() + 60_000).toISOString(),
          accepted_at: null,
          requires_study_documents: false,
        },
        next_action: "portal",
      }), 20))
    );

    const { controller } = createControllerWithStates();

    await Promise.all([
      controller.handleUrl("https://participant.staging.politis.co.uk/join-study?token=dup"),
      controller.handleUrl("https://participant.staging.politis.co.uk/join-study?token=dup"),
    ]);

    expect(mockedExchange).toHaveBeenCalledTimes(1);
  });

  it("incoming invitation supersedes an in-flight session restore", async () => {
    mockedSaveSessionMaterial.mockResolvedValue(undefined);
    mockedLoadSessionMaterial.mockResolvedValue({
      accessToken: "token-restore",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });

    const restore = deferredPromise<{
      session: { expires_at: string; revocable: true };
      participant: { display_name: string; consent_status: "granted" };
      invitation: { study_id: number; invitation_status: "valid" | "accepted"; expires_at: string; accepted_at: string | null; requires_study_documents: boolean };
      next_action: "consent_required" | "portal";
      study_scope: number[];
    }>();
    mockedGetCurrentSession.mockImplementation(() => restore.promise);
    mockedExchange.mockResolvedValue({
      session: {
        access_token: "token-fresh",
        token_type: "Bearer",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        revocable: true,
      },
      participant: {
        display_name: "Fresh",
        consent_status: "granted",
      },
      invitation: {
        study_id: 8,
        invitation_status: "valid",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        accepted_at: null,
        requires_study_documents: false,
      },
      next_action: "portal",
    });

    const { controller } = createControllerWithStates();
    const restorePromise = controller.restoreSession();
    await controller.handleUrl("https://participant.staging.politis.co.uk/join-study?token=newtoken");

    restore.resolve({
      session: { expires_at: new Date(Date.now() + 60_000).toISOString(), revocable: true },
      participant: {
        display_name: "Old",
        consent_status: "granted",
      },
      invitation: { study_id: 1, invitation_status: "accepted", expires_at: new Date(Date.now() + 60_000).toISOString(), accepted_at: new Date().toISOString(), requires_study_documents: false },
      next_action: "portal",
      study_scope: [1],
    });
    await restorePromise;

    expect(controller.getState()).toEqual({
      status: "authenticated",
      participantDisplayName: "Fresh",
      studyScope: [8],
    });
  });

  it("retry re-attempts the last invitation after a recoverable exchange failure", async () => {
    mockedSaveSessionMaterial.mockResolvedValue(undefined);
    mockedLinking.getInitialURL.mockResolvedValue(
      "https://participant.staging.politis.co.uk/join-study?token=retryme"
    );
    mockedExchange
      .mockRejectedValueOnce(new ApiRequestError({ status: 429, message: "Too many requests" }))
      .mockResolvedValueOnce({
        session: {
          access_token: "token-retry",
          token_type: "Bearer",
          expires_at: new Date(Date.now() + 60_000).toISOString(),
          revocable: true,
        },
        participant: {
          display_name: "Jordan",
          consent_status: "granted",
        },
        invitation: {
          study_id: 31,
          invitation_status: "valid",
          expires_at: new Date(Date.now() + 60_000).toISOString(),
          accepted_at: null,
          requires_study_documents: false,
        },
        next_action: "portal",
      });

    const { controller } = createControllerWithStates();
    await controller.initialise();
    expect(controller.getState()).toEqual({ status: "recoverable_error", reason: "rate_limited" });

    await controller.retry();

    expect(mockedExchange).toHaveBeenCalledTimes(2);
    expect(controller.getState()).toEqual({
      status: "authenticated",
      participantDisplayName: "Jordan",
      studyScope: [31],
    });
  });

  it("clears local credentials even if logout revocation fails", async () => {
    mockedLoadSessionMaterial.mockResolvedValue({
      accessToken: "token-123",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    mockedRevokeCurrentSession.mockRejectedValue(new Error("server unavailable"));

    const { controller } = createControllerWithStates();
    await controller.signOut();

    expect(mockedClearSessionMaterial).toHaveBeenCalled();
    expect(controller.getState()).toEqual({ status: "signed_out" });
  });

  it("ignores stale exchange completion after sign-out", async () => {
    const exchange = deferredPromise<{
      session: { access_token: string; token_type: "Bearer"; expires_at: string; revocable: true };
      participant: { display_name: string; consent_status: "granted" };
      invitation: { study_id: number; invitation_status: "valid"; expires_at: string; accepted_at: null; requires_study_documents: boolean };
      next_action: "portal";
    }>();
    mockedExchange.mockImplementation(() => exchange.promise);
    mockedLoadSessionMaterial.mockResolvedValue(null);

    const { controller } = createControllerWithStates();
    const handlePromise = controller.handleUrl("https://participant.staging.politis.co.uk/join-study?token=late");
    await controller.signOut();

    exchange.resolve({
      session: {
        access_token: "late-token",
        token_type: "Bearer",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        revocable: true,
      },
      participant: {
        display_name: "Late",
        consent_status: "granted",
      },
      invitation: {
        study_id: 4,
        invitation_status: "valid",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        accepted_at: null,
        requires_study_documents: false,
      },
      next_action: "portal",
    });
    await handlePromise;

    expect(controller.getState()).toEqual({ status: "signed_out" });
  });

  it("preserves a potentially valid saved session on restore network failure", async () => {
    mockedLoadSessionMaterial.mockResolvedValue({
      accessToken: "token-123",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    mockedGetCurrentSession.mockRejectedValue(
      new ApiRequestError({ status: 0, message: "Network request failed", kind: "network" })
    );

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(mockedClearSessionMaterial).not.toHaveBeenCalled();
    expect(controller.getState()).toEqual({ status: "recoverable_error", reason: "network" });
  });

  it("clears revoked session on 401 restore", async () => {
    mockedLoadSessionMaterial.mockResolvedValue({
      accessToken: "token-123",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    mockedGetCurrentSession.mockRejectedValue(
      new ApiRequestError({ status: 401, message: "Unauthorized" })
    );

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(mockedClearSessionMaterial).toHaveBeenCalled();
    expect(controller.getState()).toEqual({ status: "terminal_error", reason: "revoked_session" });
  });

  it("sign out clears session and returns signed out", async () => {
    mockedLoadSessionMaterial.mockResolvedValue({
      accessToken: "token-123",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    mockedRevokeCurrentSession.mockResolvedValue({ revoked: true, revoked_at: null });

    const { controller } = createControllerWithStates();
    await controller.signOut();

    expect(mockedClearSessionMaterial).toHaveBeenCalled();
    expect(controller.getState()).toEqual({ status: "signed_out" });
  });
});
