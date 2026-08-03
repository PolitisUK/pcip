import { parseInvitationLink, parseInvitationTokenFromUrl } from "./deepLinks";

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

  it("extracts token from custom scheme path variant", () => {
    const token = parseInvitationTokenFromUrl("pcip-participant:///join-study?token=mobiletoken123");
    expect(token).toBe("mobiletoken123");
  });

  it("rejects missing token", () => {
    const token = parseInvitationTokenFromUrl(
      "https://participant.staging.politis.co.uk/join-study"
    );
    expect(token).toBeNull();
  });

  it("supports percent-encoded tokens", () => {
    const token = parseInvitationTokenFromUrl(
      "https://participant.staging.politis.co.uk/join-study?token=abc%252B123"
    );
    expect(token).toBe("abc+123");
  });

  it("ignores unrelated links", () => {
    const token = parseInvitationTokenFromUrl(
      "https://participant.staging.politis.co.uk/other-path?token=abc123token"
    );
    expect(token).toBeNull();
  });

  it("rejects malformed links", () => {
    const token = parseInvitationTokenFromUrl("not a url");
    expect(token).toBeNull();
  });
});

describe("parseInvitationLink", () => {
  it("classifies unrelated links as ignored", () => {
    expect(parseInvitationLink("https://participant.staging.politis.co.uk/other-path?token=abc")).toEqual({ kind: "ignore" });
    expect(parseInvitationLink("https://evil.example.invalid/join-study?token=abc")).toEqual({ kind: "ignore" });
  });

  it("classifies supported links without a usable token as invalid invitation", () => {
    expect(parseInvitationLink("https://participant.staging.politis.co.uk/join-study")).toEqual({ kind: "invalid_invitation" });
    expect(parseInvitationLink("https://participant.staging.politis.co.uk/join-study?token=%20%20")).toEqual({ kind: "invalid_invitation" });
  });
});
