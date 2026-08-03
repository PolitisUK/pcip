import { env } from "./env";

describe("env defaults", () => {
  it("exposes non-empty API and deep-link config", () => {
    expect(env.apiBaseUrl).toMatch(/^https?:\/\//);
    expect(env.deepLinkHost.length).toBeGreaterThan(0);
    expect(env.deepLinkScheme.length).toBeGreaterThan(0);
    expect(env.privacyUrl).toMatch(/^https?:\/\//);
    expect(env.termsUrl).toMatch(/^https?:\/\//);
    expect(env.supportUrl).toMatch(/^https?:\/\//);
  });
});
