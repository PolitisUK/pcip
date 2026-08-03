import { ApiRequestError, apiRequest } from "./client";

describe("apiRequest", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
  });

  afterAll(() => {
    globalThis.fetch = originalFetch;
  });

  it("maps 429 with retry_after_seconds", async () => {
    globalThis.fetch = jest.fn(async () =>
      new Response(
        JSON.stringify({
          error: { code: "rate_limited", message: "Too many requests" },
          retry_after_seconds: 30,
        }),
        {
          status: 429,
          headers: { "Content-Type": "application/json", "Retry-After": "30" },
        }
      )
    ) as typeof fetch;

    await expect(apiRequest("/test")).rejects.toMatchObject({
      status: 429,
      code: "rate_limited",
      retryAfterSeconds: 30,
    } satisfies Partial<ApiRequestError>);
  });

  it("maps network failure", async () => {
    globalThis.fetch = jest.fn(async () => {
      throw new Error("socket hang up");
    }) as typeof fetch;

    await expect(apiRequest("/test")).rejects.toMatchObject({
      kind: "network",
      status: 0,
    } satisfies Partial<ApiRequestError>);
  });

  it("sends bearer token without exposing it in errors", async () => {
    globalThis.fetch = jest.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    ) as typeof fetch;

    await apiRequest("/test", { accessToken: "secret-token" });

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const call = jest.mocked(globalThis.fetch).mock.calls[0];
    expect((call[1] as RequestInit).headers).toMatchObject({
      Authorization: "Bearer secret-token",
    });
  });
});
