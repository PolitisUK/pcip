import { parseInvitationTokenFromUrl } from "./deepLinks";

describe("parseInvitationTokenFromUrl", () => {
  it("extracts token from allowed HTTPS invitation link", () => {
    const token = parseInvitationTokenFromUrl(
      "https://participant.staging.politis.co.uk/join-study?token=abc123token"
    );
    expect(token).toBe("abc123token");
  });

  it("rejects unknown host", () => {
    const token = parseInvitationTokenFromUrl(
      "https://evil.example.invalid/join-study?token=abc123token"
    );
    expect(token).toBeNull();
  });

  it("extracts token from custom scheme invitation link", () => {
    const token = parseInvitationTokenFromUrl("pcip-participant://join-study?token=mobiletoken123");
    expect(token).toBe("mobiletoken123");
  });

  it("rejects missing token", () => {
    const token = parseInvitationTokenFromUrl(
      "https://participant.staging.politis.co.uk/join-study"
    );
    expect(token).toBeNull();
  });
});
