import * as SecureStore from "expo-secure-store";

import {
  clearSessionMaterial,
  loadSessionMaterial,
  saveSessionMaterial,
} from "./sessionStore";

jest.mock("expo-secure-store", () => ({
  setItemAsync: jest.fn(),
  getItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockedSecureStore = jest.mocked(SecureStore);

describe("sessionStore", () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it("stores minimal session material securely", async () => {
    await saveSessionMaterial({
      accessToken: "access-token",
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
      participantId: 101,
      participantDisplayName: "Sam",
      consentStatus: "granted",
      studyScope: [7],
    });

    expect(mockedSecureStore.setItemAsync).toHaveBeenCalled();
  });

  it("loads and validates session material", async () => {
    const expiresAt = new Date(Date.now() + 60_000).toISOString();
    mockedSecureStore.getItemAsync
      .mockResolvedValueOnce("access-token")
      .mockResolvedValueOnce(expiresAt)
      .mockResolvedValueOnce("101")
      .mockResolvedValueOnce("Sam")
      .mockResolvedValueOnce("granted")
      .mockResolvedValueOnce("[7]");

    const loaded = await loadSessionMaterial();

    expect(loaded).toEqual({
      accessToken: "access-token",
      expiresAt,
      participantId: 101,
      participantDisplayName: "Sam",
      consentStatus: "granted",
      studyScope: [7],
    });
  });

  it("clears malformed session material safely", async () => {
    mockedSecureStore.getItemAsync
      .mockResolvedValueOnce("access-token")
      .mockResolvedValueOnce("not-a-date")
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null);

    const loaded = await loadSessionMaterial();

    expect(loaded).toBeNull();
    expect(mockedSecureStore.deleteItemAsync).toHaveBeenCalled();
  });

  it("clears session on sign out", async () => {
    await clearSessionMaterial();
    expect(mockedSecureStore.deleteItemAsync).toHaveBeenCalled();
  });
});
