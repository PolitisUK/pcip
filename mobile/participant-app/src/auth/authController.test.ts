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
        participant_id: 99,
        display_name: "Alex",
        consent_status: "granted",
      },
      study_scope: [15],
    });

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(controller.getState()).toEqual({
      status: "authenticated",
      participantDisplayName: "Alex",
      participantId: 99,
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
        participant_id: 12,
        display_name: "Pat",
        consent_status: "pending",
      },
      invitation: {
        study_id: 22,
        invitation_status: "valid",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        accepted_at: null,
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
        participant_id: 12,
        display_name: "Pat",
        consent_status: "granted",
      },
      invitation: {
        study_id: 22,
        invitation_status: "valid",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
        accepted_at: null,
      },
      next_action: "portal",
    });
    mockedSaveSessionMaterial.mockRejectedValue(new Error("Secure storage unavailable"));

    const { controller } = createControllerWithStates();
    await controller.initialise();

    expect(controller.getState()).toEqual({ status: "recoverable_error", reason: "secure_storage" });
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
          participant_id: 9,
          display_name: "Casey",
          consent_status: "granted",
        },
        invitation: {
          study_id: 88,
          invitation_status: "valid",
          expires_at: new Date(Date.now() + 60_000).toISOString(),
          accepted_at: null,
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
          participant_id: 21,
          display_name: "Jordan",
          consent_status: "granted",
        },
        invitation: {
          study_id: 31,
          invitation_status: "valid",
          expires_at: new Date(Date.now() + 60_000).toISOString(),
          accepted_at: null,
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
      participantId: 21,
      studyScope: [31],
    });
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
