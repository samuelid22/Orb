import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

function check(overrides = {}) {
  return execFileSync(process.execPath, ["scripts/check-vercel-env.mjs"], {
    cwd: process.cwd(), encoding: "utf8", stdio: "pipe",
    env: { ...process.env, VERCEL_GIT_COMMIT_REF: "usdg-test", VERCEL_ENV: "preview",
      VITE_ORB_DEPLOYMENT_TARGET: "usdg-staging", VITE_API_BASE_URL: "https://staging.example.invalid", ...overrides },
  });
}

describe("USDG staging deployment isolation", () => {
  it("allows a separate staging API for Preview", () => expect(check()).toContain("API origin is configured"));
  it("rejects the production API", () => expect(() => check({ VITE_API_BASE_URL: "https://orb-api-7qwv.onrender.com" })).toThrow());
  it("rejects production deployments and missing staging designation", () => {
    expect(() => check({ VERCEL_ENV: "production" })).toThrow();
    expect(() => check({ VITE_ORB_DEPLOYMENT_TARGET: "" })).toThrow();
  });
  it("preserves native main build configuration and disables automatic USDG branch deployments", () => {
    expect(check({ VERCEL_GIT_COMMIT_REF: "main", VERCEL_ENV: "production", VITE_ORB_DEPLOYMENT_TARGET: "",
      VITE_API_BASE_URL: "https://orb-api-7qwv.onrender.com" })).toContain("API origin is configured");
    const config = JSON.parse(readFileSync("vercel.json", "utf8"));
    expect(config.git.deploymentEnabled["usdg-test"]).toBe(false);
    expect(config.git.deploymentEnabled.main).toBeUndefined();
  });
});
