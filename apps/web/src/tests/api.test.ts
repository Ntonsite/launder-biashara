import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, sessions } from "../lib/api";

const session = {
  access_token: "old",
  refresh_token: "r1",
  user: { id: "u", name: "N", role: "CUSTOMER", language: "en" },
};
const json = (status: number, body: unknown) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("api client", () => {
  it("refreshes an expired session once and retries the request", async () => {
    sessions.set("customer", session);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        json(401, { error: { code: "TOKEN_EXPIRED", message: "expired" } }),
      )
      .mockResolvedValueOnce(
        json(200, { ...session, access_token: "new", refresh_token: "r2" }),
      )
      .mockResolvedValueOnce(json(200, { ok: true }));
    await expect(
      api("/api/v1/customer/orders", { auth: "customer" }),
    ).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      (fetchMock.mock.calls[2][1]!.headers as Record<string, string>)
        .Authorization,
    ).toBe("Bearer new");
    expect(sessions.get("customer")?.refresh_token).toBe("r2");
  });

  it("clears the session when refresh fails", async () => {
    sessions.set("customer", session);
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        json(401, { error: { code: "TOKEN_EXPIRED", message: "expired" } }),
      )
      .mockResolvedValueOnce(
        json(401, { error: { code: "SESSION_EXPIRED", message: "gone" } }),
      );
    await expect(
      api("/api/v1/customer/orders", { auth: "customer" }),
    ).rejects.toMatchObject({ status: 401 });
    expect(sessions.get("customer")).toBeNull();
  });

  it("maps the error envelope and network failures to ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      json(409, {
        error: {
          code: "PRICE_CHANGED",
          message: "changed",
          details: { quote: { total: 1 } },
        },
      }),
    );
    const err = await api("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 409,
      code: "PRICE_CHANGED",
      details: { quote: { total: 1 } },
    });
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(
      new TypeError("Failed to fetch"),
    );
    await expect(api("/x")).rejects.toMatchObject({ code: "NETWORK" });
  });
});
