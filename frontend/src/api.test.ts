import { describe, expect, it } from "vitest";
import { apiUrl } from "./api";

describe("apiUrl", () => {
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
});
