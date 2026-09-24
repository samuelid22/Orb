import { describe, expect, it } from "vitest";
import { apiUrl } from "./api-url.js";

describe("apiUrl", () => {
  it("keeps paths same-origin when no base URL is configured", () => {
    expect(apiUrl("/api/health", "")).toBe("/api/health");
  });

  it("joins a configured origin without trailing slashes", () => {
    expect(apiUrl("/api/health", "https://orb-api.example.com/")).toBe(
      "https://orb-api.example.com/api/health",
    );
  });

  it("rejects non-HTTP base URLs", () => {
    expect(() => apiUrl("/api/health", "ftp://invalid.example")).toThrow("HTTP(S)");
  });
});
