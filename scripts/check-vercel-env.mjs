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

console.log("Orb production API origin is configured.");
