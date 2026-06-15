import { afterEach, describe, expect, it, vi } from "vitest";
import {
  apiUrl,
  clearStoredAccessToken,
  fetchProducts,
  getStoredAccessToken,
  loginAdmin,
  setUnauthorizedHandler,
  storeAccessToken,
} from "./api";

describe("apiUrl", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearStoredAccessToken();
    setUnauthorizedHandler(null);
  });

  it("uses the local backend fallback when no base URL is supplied", () => {
    expect(apiUrl("/health", "http://127.0.0.1:8000")).toBe(
      "http://127.0.0.1:8000/health",
    );
  });

  it("normalizes a trailing slash on the configured backend URL", () => {
    expect(apiUrl("/products/", "https://purchasing-ai-api.onrender.com/")).toBe(
      "https://purchasing-ai-api.onrender.com/products/",
    );
  });

  it("stores the bearer token in sessionStorage after login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ access_token: "abc123", token_type: "bearer", expires_in: 3600 }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await loginAdmin({ email: "admin@example.com", password: "secret-password" });

    expect(getStoredAccessToken()).toBe("abc123");
  });

  it("adds bearer token to authenticated API requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    storeAccessToken("stored-token");

    await fetchProducts();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/products/"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer stored-token" }),
      }),
    );
  });

  it("clears token and notifies app on protected 401 responses", async () => {
    const onUnauthorized = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Invalid or expired authentication credentials." }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    storeAccessToken("expired-token");
    setUnauthorizedHandler(onUnauthorized);

    await expect(fetchProducts()).rejects.toThrow("Invalid or expired authentication credentials.");

    expect(getStoredAccessToken()).toBeNull();
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
});
