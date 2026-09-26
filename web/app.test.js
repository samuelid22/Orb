import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const html = readFileSync(resolve(process.cwd(), "web/index.html"), "utf8");

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function isInspectUrl(url) {
  return /\/api\/orb\/(decode|compose)\/file(\?|$)/.test(String(url));
}

function isUploadPingUrl(url) {
  return /\/api\/upload-ping(\?|$)/.test(String(url));
}

function inspectCalls(fetchMock = globalThis.fetch) {
  return fetchMock.mock.calls.filter(([url]) => isInspectUrl(url));
}

async function flush() {
  for (let index = 0; index < 6; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function chooseVideo(name = "clip.mp4") {
  const input = document.getElementById("file-input");
  Object.defineProperty(input, "files", {
    value: [new File(["video-data"], name, { type: "video/mp4" })],
    configurable: true,
  });
  input.dispatchEvent(new Event("change"));
}

function mockApi({
  inspectError = null,
  healthOk = true,
  readyOk = true,
  pingStatus = 204,
  jobStatuses = [],
  jobError = null,
} = {}) {
  let inspectNumber = 0;
  const fetchMock = vi.fn(async (url, options = {}) => {
    const path = String(url);
    if (path === "/api/orb/credits/config") return response({ enabled: false, chain_id: 421614, price_wei: "1000000000000" });
    if (path === "/api/health") return response({ status: healthOk ? "ok" : "unavailable" }, healthOk ? 200 : 503);
    if (path === "/api/ready") return response({ status: readyOk ? "ready" : "starting" }, readyOk ? 200 : 503);
    if (isUploadPingUrl(path)) return response({}, pingStatus);
    if (isInspectUrl(path)) {
      if (inspectError) throw inspectError;
      inspectNumber += 1;
      return response({ job_id: `job-${inspectNumber}` }, 202);
    }
    if (path === "/api/orb/enhance") return response({ job_id: "job-enhance" }, 202);
    if (path.startsWith("/api/jobs/") && path.endsWith("/result")) {
      const id = path.split("/")[3];
      return response({
        job_id: id,
        operation: id === "job-enhance" ? "enhance" : "decode",
        provider: "gemini",
        video: id === "job-enhance" ? undefined : { name: "clip.mp4", duration: 2, width: 320, height: 240, fps: 24, preview_url: `/api/jobs/${id}/frames/source.mp4` },
        summary: "One scene detected.",
        scenes: id === "job-enhance" ? [] : [{ index: 0, start: 0, end: 2, duration: 2, frames: [] }],
        visual_analysis: { composition: "Centered subject" },
        original_prompt: id === "job-enhance" ? "a blue car" : undefined,
        prompt: "A blue car under soft daylight.",
        notice: "Exact original prompt cannot be guaranteed.",
      });
    }
    if (path.startsWith("/api/jobs/")) {
      if (jobError) throw jobError;
      const job = jobStatuses.length ? jobStatuses.shift() : { state: "complete", stage: "Complete" };
      return response(job);
    }
    throw new Error(`Unexpected request: ${path}`);
  });
  globalThis.fetch = fetchMock;
  return fetchMock;
}

async function startPaidJobWithExpiredSession({ released = false } = {}) {
  const owner = `0x${"11".repeat(20)}`;
  const other = `0x${"22".repeat(20)}`;
  const jobId = "a".repeat(32);
  const handlers = new Map();
  let selectedAccount = owner;
  let signIns = 0;
  let available = 1;
  const provider = {
    on: vi.fn((event, listener) => handlers.set(event, listener)),
    request: vi.fn(async ({ method }) => {
      if (method === "eth_accounts" || method === "eth_requestAccounts") return [selectedAccount];
      if (method === "eth_chainId") return "0x66eee";
      if (method === "personal_sign") return `0x${"cd".repeat(65)}`;
      throw new Error(`Unexpected wallet method: ${method}`);
    }),
  };
  window.ethereum = provider;
  const fetchMock = vi.fn(async (url, options = {}) => {
    const path = String(url);
    if (path === "/api/orb/credits/config") return response({ enabled: true, chain_id: 421614, price_wei: "1000" });
    if (path === "/api/health") return response({ status: "ok", orb_ai_access: "credits" });
    if (path === "/api/ready") return response({ status: "ready" });
    if (isUploadPingUrl(path)) return response({}, 204);
    if (path === "/api/orb/wallet/challenge") return response({ nonce: `nonce-${signIns}`, message: "Sign in to Orb" });
    if (path === "/api/orb/wallet/sign-in") return response({ wallet: selectedAccount,
      token: `session-${++signIns}`, expires_at: Math.floor(Date.now() / 1000) + 3600 });
    if (path === "/api/orb/credits/balance") return response({ wallet: selectedAccount, available });
    if (isInspectUrl(path)) return response({ job_id: jobId }, 202);
    if (path === `/api/jobs/${jobId}`) {
      if (options.headers?.Authorization === "Bearer session-1") {
        available = 0;
        return response({ detail: "Wallet session expired. Sign again." }, 401);
      }
      if (selectedAccount !== owner) return response({ detail: "Unknown job." }, 404);
      if (released) {
        available = 1;
        return response({ state: "error", stage: "Interrupted", error: "AI processing failed." });
      }
      return response({ state: "complete", stage: "Complete" });
    }
    if (path === `/api/jobs/${jobId}/result`) return response({ job_id: jobId, operation: "decode",
      provider: "gemini", video: { name: "clip.mp4", duration: 2, width: 320, height: 240 },
      scenes: [], prompt: "Recovered durable prompt.", visual_analysis: {} });
    throw new Error(`Unexpected request: ${path}`);
  });
  globalThis.fetch = fetchMock;
  await import("./app.js");
  await flush();
  document.getElementById("wallet-connect").click();
  await flush();
  chooseVideo();
  document.getElementById("decode-btn").click();
  await flush();
  return { owner, other, jobId, provider, fetchMock, changeAccount(next) {
    selectedAccount = next;
    handlers.get("accountsChanged")?.([next]);
  } };
}

describe("Orb frontend", () => {
  beforeEach(() => {
    vi.resetModules();
    delete window.ethereum;
    sessionStorage.clear();
    document.open();
    document.write(html);
    document.close();
    window.scrollTo = vi.fn();
    HTMLElement.prototype.focus = vi.fn();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows all three working modes in the approved layout", async () => {
    mockApi();
    await import("./app.js");
    await flush();

    expect(document.querySelector(".wordmark").textContent).toBe("Orb");
    expect(document.querySelector(".mode-pill.active").textContent).toBe("Decode");
    expect(document.querySelectorAll(".mode-pill")).toHaveLength(3);
    expect(document.getElementById("mode-compose").disabled).toBe(false);
    expect(document.getElementById("mode-enhance").disabled).toBe(false);
    expect(document.querySelector(".mode-cards")).toBeNull();
    expect(document.querySelector(".mode-nav")).toBeNull();
    expect(document.querySelector("#dropzone small").textContent).toContain("WebP");
  });

  it("connects on Arbitrum Sepolia, verifies a testnet purchase, and enables paid AI", async () => {
    const address = `0x${"11".repeat(20)}`;
    const receiver = `0x${"22".repeat(20)}`;
    const txHash = `0x${"ab".repeat(32)}`;
    const paidJobId = "f".repeat(32);
    let chain = "0x1";
    let available = 0;
    const provider = {
      on: vi.fn(),
      request: vi.fn(async ({ method, params }) => {
        if (method === "eth_accounts") return [address];
        if (method === "eth_requestAccounts") return [address];
        if (method === "eth_chainId") return chain;
        if (method === "wallet_switchEthereumChain") { chain = params[0].chainId; return null; }
        if (method === "personal_sign") return `0x${"cd".repeat(65)}`;
        if (method === "eth_sendTransaction") return txHash;
        throw new Error(`Unexpected wallet method: ${method}`);
      }),
    };
    window.ethereum = provider;
    const fetchMock = vi.fn(async (url, options = {}) => {
      const path = String(url);
      if (path === "/api/orb/credits/config") return response({ enabled: true, chain_id: 421614, price_wei: "1000000000000" });
      if (path === "/api/health") return response({ status: "ok", orb_ai_access: "credits" });
      if (path === "/api/ready") return response({ status: "ready" });
      if (isUploadPingUrl(path)) return response({}, 204);
      if (path === "/api/orb/wallet/challenge") return response({ nonce: "nonce", message: "Sign in to Orb testnet" });
      if (path === "/api/orb/wallet/sign-in") return response({ wallet: address, token: "session-token",
        expires_at: Math.floor(Date.now() / 1000) + 3600 });
      if (path === "/api/orb/credits/balance") return response({ wallet: address, available });
      if (path === "/api/orb/credits/quotes") return response({ quote_id: "quote", chain_id: 421614,
        to: receiver, value_wei: "1000000000000", data: "0x4f524231abcd" });
      if (path === "/api/orb/credits/quotes/quote/verify") {
        available = 1;
        return response({ credits: 1, balance: { available } });
      }
      if (isInspectUrl(path)) return response({ job_id: paidJobId }, 202);
      if (path === `/api/jobs/${paidJobId}`) return response({ state: "processing", stage: "Analyzing image" });
      throw new Error(`Unexpected request: ${path}`);
    });
    globalThis.fetch = fetchMock;
    await import("./app.js");
    await flush();
    chooseVideo();
    expect(document.getElementById("decode-btn").disabled).toBe(true);
    expect(document.getElementById("upload-credits-cta").classList.contains("hidden")).toBe(false);
    document.getElementById("upload-credits-cta").click();
    document.getElementById("wallet-connect").click();
    await flush();
    expect(provider.request.mock.calls.some(([arg]) => arg.method === "wallet_switchEthereumChain")).toBe(true);
    expect(document.getElementById("wallet-network").textContent).toContain("Arbitrum Sepolia");
    expect(document.getElementById("wallet-address").textContent).toContain("0x1111");
    document.getElementById("wallet-buy").click();
    await flush();
    expect(provider.request.mock.calls.find(([arg]) => arg.method === "eth_sendTransaction")[0].params[0]).toMatchObject({
      from: address, to: receiver, data: "0x4f524231abcd",
    });
    expect(document.getElementById("wallet-balance").textContent).toContain("1 testnet credit");
    expect(document.getElementById("decode-btn").disabled).toBe(false);
    document.getElementById("wallet-close").click();
    document.getElementById("decode-btn").click();
    await flush();
    const request = inspectCalls(fetchMock)[0][1];
    expect(request.headers.Authorization).toBe("Bearer session-token");
    expect(request.headers["X-Orb-Idempotency-Key"]).toBeTruthy();
    expect(JSON.parse(sessionStorage.getItem("orb-active-paid-job")).jobId).toBe(paidJobId);
    expect(document.getElementById("screen-processing").classList.contains("hidden")).toBe(false);
  });

  it("pauses a paid 401 and resumes the same job and durable result after signing again", async () => {
    const { jobId, provider, fetchMock } = await startPaidJobWithExpiredSession();
    expect(document.getElementById("job-error").textContent).toBe(
      "Your session expired. Sign again to continue this analysis.");
    expect(document.getElementById("wallet-panel").classList.contains("hidden")).toBe(false);
    expect(document.getElementById("wallet-connect").textContent).toBe("Sign again");
    expect(JSON.parse(sessionStorage.getItem("orb-active-paid-job")).jobId).toBe(jobId);
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === `/api/jobs/${jobId}`)).toHaveLength(1);

    document.getElementById("wallet-connect").click();
    await flush();
    expect(provider.request.mock.calls.filter(([request]) => request.method === "personal_sign")).toHaveLength(2);
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === `/api/jobs/${jobId}`)).toHaveLength(2);
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === `/api/jobs/${jobId}/result`)).toHaveLength(1);
    expect(inspectCalls(fetchMock)).toHaveLength(1);
    expect(document.getElementById("res-prompt").textContent).toBe("Recovered durable prompt.");
    expect(sessionStorage.getItem("orb-active-paid-job")).toBeNull();
  });

  it("keeps an expired paid job private when a different wallet signs in", async () => {
    const { other, jobId, changeAccount, fetchMock } = await startPaidJobWithExpiredSession();
    changeAccount(other);
    document.getElementById("wallet-connect").click();
    await flush();
    expect(document.getElementById("wallet-connect").textContent).toBe("Connected");
    expect(document.getElementById("job-error").textContent).toContain("wallet that started this analysis");
    expect(JSON.parse(sessionStorage.getItem("orb-active-paid-job")).jobId).toBe(jobId);
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === `/api/jobs/${jobId}`)).toHaveLength(1);
    expect(inspectCalls(fetchMock)).toHaveLength(1);
  });

  it("refreshes the restored credit balance when a resumed paid job failed", async () => {
    const { jobId, fetchMock } = await startPaidJobWithExpiredSession({ released: true });
    document.getElementById("wallet-connect").click();
    await flush();
    expect(document.getElementById("job-error").textContent).toContain("Analysis failed");
    expect(document.getElementById("wallet-balance").textContent).toContain("1 testnet credit available");
    expect(sessionStorage.getItem("orb-active-paid-job")).toBeNull();
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === `/api/jobs/${jobId}`)).toHaveLength(2);
    expect(inspectCalls(fetchMock)).toHaveLength(1);
  });

  it("opens a grouped menu, closes outside and on Escape, and shows About Orb", async () => {
    mockApi();
    await import("./app.js");
    await flush();

    const input = document.getElementById("file-input");
    const filePicker = vi.spyOn(input, "click").mockImplementation(() => {});
    document.getElementById("choose-file-btn").click();
    expect(filePicker).toHaveBeenCalledTimes(1);

    const toggle = document.getElementById("menu-toggle");
    const menu = document.getElementById("site-menu");
    toggle.click();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(menu.classList.contains("hidden")).toBe(false);
    expect(Array.from(menu.querySelectorAll(".menu-heading")).map((item) => item.textContent)).toEqual([
      "Home", "Workspace", "Account", "Information",
    ]);
    expect(menu.querySelectorAll(".menu-action")).toHaveLength(3);
    expect(menu.querySelectorAll(".menu-unavailable")).toHaveLength(2);
    expect(Array.from(menu.querySelectorAll(".menu-unavailable small")).every((item) => item.textContent === "Coming soon")).toBe(true);
    expect(menu.querySelector("#menu-upload")).toBeNull();

    document.body.click();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    toggle.click();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.focus).toHaveBeenCalled();

    toggle.click();
    document.getElementById("menu-about").click();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById("about-panel").classList.contains("hidden")).toBe(false);
    expect(document.getElementById("about-panel").textContent).toContain("Reconstruct a plausible prompt");
    document.getElementById("about-close").click();
    toggle.click();
    document.getElementById("menu-wallet").click();
    expect(document.getElementById("wallet-panel").classList.contains("hidden")).toBe(false);
    expect(document.getElementById("wallet-panel").textContent).toContain("TESTNET ONLY");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(document.getElementById("wallet-panel").classList.contains("hidden")).toBe(true);
    expect(document.getElementById("about-panel").textContent).toContain("Refine an existing generation prompt");
    document.getElementById("about-close").click();
    expect(document.getElementById("about-panel").classList.contains("hidden")).toBe(true);
  });

  it("keeps Decode disabled until the service passes health, ready, and the upload canary", async () => {
    const fetchMock = mockApi({ healthOk: false });
    await import("./app.js");
    await flush();

    expect(document.getElementById("decode-btn").disabled).toBe(true);
    expect(document.getElementById("decode-btn").querySelector("span").textContent).toBe("Initializing");
    expect(inspectCalls(fetchMock)).toHaveLength(0);
  });

  it("enables Decode after the upload-path canary succeeds", async () => {
    mockApi();
    await import("./app.js");
    await flush();

    // Service is ready but no file is chosen: the button still waits.
    const button = document.getElementById("decode-btn");
    expect(document.getElementById("service-status").textContent).toContain("ready");
    expect(button.disabled).toBe(true);
    chooseVideo();
    expect(button.disabled).toBe(false);
    expect(button.querySelector("span").textContent).toBe("Decode reference");
  });

  it("accepts image files and rejects unsupported files before upload", async () => {
    const fetchMock = mockApi();
    await import("./app.js");
    await flush();
    chooseVideo("snapshot.png");
    await flush();

    expect(document.getElementById("decode-btn").disabled).toBe(false);
    chooseVideo("snapshot.gif");
    expect(document.getElementById("upload-error").textContent).toContain("Unsupported file type");
    expect(inspectCalls(fetchMock)).toHaveLength(0);
  });

  it("runs one correlated upload and renders the reconstructed prompt", async () => {
    const fetchMock = mockApi({
      jobStatuses: [{ state: "complete", stage: "Complete" }],
    });
    await import("./app.js");
    await flush();
    chooseVideo();
    document.getElementById("decode-btn").click();
    await flush();

    const inspect = inspectCalls(fetchMock);
    expect(inspect).toHaveLength(1);
    expect(inspect[0][0]).toMatch(/^\/api\/orb\/decode\/file\?upload_attempt_id=[A-Za-z0-9-]+$/);
    expect(inspect[0][1].method).toBe("POST");
    expect(inspect[0][1].body).toBeInstanceOf(FormData);
    expect(inspect[0][1].headers?.["Content-Type"]).toBeUndefined();

    expect(document.getElementById("screen-results").classList.contains("hidden")).toBe(false);
    expect(document.getElementById("res-title").textContent).toBe("clip.mp4");
    expect(document.querySelectorAll("#res-scenes .scene")).toHaveLength(1);
    expect(document.getElementById("res-prompt").textContent).toContain("A blue car");
    expect(document.getElementById("res-notice").textContent).toContain("cannot be guaranteed");
  });

  it("labels an interrupted upload without retrying", async () => {
    const fetchMock = mockApi({ inspectError: new TypeError("Failed to fetch") });
    await import("./app.js");
    await flush();
    chooseVideo();
    document.getElementById("decode-btn").click();
    await flush();

    const message = document.getElementById("job-error").textContent;
    expect(message).toContain("Upload connection was interrupted");
    expect(message).toContain("No retry was made");
    expect(message).toContain("Reference:");
    expect(inspectCalls(fetchMock)).toHaveLength(1);
  });

  it("blocks an unreadable file before any upload and guides to another source", async () => {
    const fetchMock = mockApi();
    await import("./app.js");
    await flush();
    chooseVideo();
    const file = document.getElementById("file-input").files[0];
    vi.spyOn(file, "slice").mockReturnValue({
      arrayBuffer: () => Promise.reject(new DOMException("denied", "NotReadableError")),
    });
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    document.getElementById("decode-btn").click();
    await flush();

    expect(inspectCalls(fetchMock)).toHaveLength(0);
    const message = document.getElementById("job-error").textContent;
    expect(message).toContain("couldn't be accessed through the selected source");
    expect(message).toContain("(NotReadableError)");
    expect(message).toContain("Reference:");
    expect(info).toHaveBeenCalledWith(expect.stringContaining("precheck=unreadable"));
  });

  it("returns to the upload screen from results", async () => {
    mockApi();
    await import("./app.js");
    await flush();
    chooseVideo();
    document.getElementById("decode-btn").click();
    await flush();

    document.getElementById("menu-toggle").click();
    document.getElementById("menu-home").click();
    expect(document.getElementById("screen-home").classList.contains("hidden")).toBe(false);
    expect(document.getElementById("screen-results").classList.contains("hidden")).toBe(true);
    expect(document.getElementById("site-menu").classList.contains("hidden")).toBe(true);
    expect(document.getElementById("file-input").value).toBe("");
  });

  it("composes from an image and prevents repeated submission", async () => {
    const fetchMock = mockApi();
    await import("./app.js");
    await flush();
    document.getElementById("mode-compose").click();
    chooseVideo("reference.png");
    const button = document.getElementById("decode-btn");
    button.click();
    button.click();
    await flush();
    expect(inspectCalls(fetchMock)).toHaveLength(1);
    expect(inspectCalls(fetchMock)[0][0]).toContain("/api/orb/compose/file");
  });

  it("enhances a prompt and copies the result", async () => {
    const fetchMock = mockApi();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(async () => {}) }, configurable: true });
    await import("./app.js");
    await flush();
    document.getElementById("mode-enhance").click();
    const input = document.getElementById("prompt-input");
    input.value = "a blue car";
    input.dispatchEvent(new Event("input"));
    document.getElementById("enhance-btn").click();
    await flush();
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === "/api/orb/enhance")).toHaveLength(1);
    expect(document.getElementById("res-original-text").textContent).toBe("a blue car");
    document.getElementById("copy-prompt").click();
    await flush();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("A blue car under soft daylight.");
  });

  it("shows prompt-specific processing labels during Enhance", async () => {
    mockApi({ jobStatuses: Array.from({ length: 10 }, () => ({ state: "processing", stage: "Enhancing prompt" })) });
    await import("./app.js");
    await flush();
    document.getElementById("mode-enhance").click();
    const input = document.getElementById("prompt-input");
    input.value = "A red balloon";
    input.dispatchEvent(new Event("input"));
    document.getElementById("enhance-btn").click();
    await flush();
    expect(document.getElementById("phase-text").textContent).toBe("Improving prompt");
    expect(document.getElementById("step-list").textContent).not.toContain("Detecting scenes");
  });
});
