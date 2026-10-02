import { execFileSync } from "node:child_process";

const value = process.env.VITE_API_BASE_URL;
let url;
try {
  url = new URL(value);
} catch {
  throw new Error("Set VITE_API_BASE_URL to the independent Orb Render HTTPS origin before building on Vercel.");
}

if (url.protocol !== "https:" || url.username || url.password ||
    url.pathname !== "/" || url.search || url.hash ||
    ["localhost", "127.0.0.1", "::1"].includes(url.hostname)) {
  throw new Error("VITE_API_BASE_URL must be the exact HTTPS origin of Orb's public backend.");
}

let branch = process.env.VERCEL_GIT_COMMIT_REF;
if (!branch) {
  try { branch = execFileSync("git", ["branch", "--show-current"], { encoding: "utf8" }).trim(); }
  catch { /* Git metadata may be absent in build artifacts. */ }
}
if (branch === "usdg-test" || process.env.VITE_ORB_DEPLOYMENT_TARGET === "usdg-staging") {
  if (process.env.VERCEL_ENV === "production" || process.env.VITE_ORB_DEPLOYMENT_TARGET !== "usdg-staging"
      || url.origin === "https://orb-api-7qwv.onrender.com") {
    throw new Error("USDG branch requires a staging API origin, VITE_ORB_DEPLOYMENT_TARGET=usdg-staging, and Preview deployment.");
  }
}
console.log("Orb API origin is configured.");
