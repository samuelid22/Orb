import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const html = readFileSync(resolve(process.cwd(), "web/index.html"), "utf8");

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function isInspectUrl(url) {
  return /\/api\/inspect(\?|$)/.test(String(url));
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
    if (path === "/api/health") return response({ status: healthOk ? "ok" : "unavailable" }, healthOk ? 200 : 503);
    if (path === "/api/ready") return response({ status: readyOk ? "ready" : "starting" }, readyOk ? 200 : 503);
    if (isUploadPingUrl(path)) return response({}, pingStatus);
    if (isInspectUrl(path)) {
      if (inspectError) throw inspectError;
      inspectNumber += 1;
      return response({ job_id: `job-${inspectNumber}` }, 202);
    }
    if (path.startsWith("/api/jobs/") && path.endsWith("/result")) {
      const id = path.split("/")[3];
      return response({
        job_id: id,
        tier: "basic",
        video: { name: "clip.mp4", duration: 2, width: 320, height: 240, fps: 24, preview_url: `/api/jobs/${id}/frames/source.mp4` },
        analyzer: { mode: "local" },
        summary: "One scene detected.",
        scenes: [{ index: 0, start: 0, end: 2, duration: 2, frames: [] }],
        prompt_markdown: "",
        breakdown: [],
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

describe("Orb frontend", () => {
  beforeEach(() => {
    vi.resetModules();
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

  it("offers only Decode while Compose and Enhance are clearly unavailable", async () => {
    mockApi();
    await import("./app.js");
    await flush();

    expect(document.getElementById("tab-decode").getAttribute("aria-pressed")).toBe("true");
    expect(document.getElementById("tab-compose").disabled).toBe(true);
    expect(document.getElementById("tab-enhance").disabled).toBe(true);
    const states = Array.from(document.querySelectorAll(".mode-state")).map((el) => el.textContent);
    expect(states).toContain("Available");
    expect(states.filter((s) => s === "Coming soon")).toHaveLength(2);
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
    expect(button.querySelector("span").textContent).toBe("Decode video");
  });

  it("rejects image files with an honest next-stage message and no upload", async () => {
    const fetchMock = mockApi();
    await import("./app.js");
    await flush();
    chooseVideo("snapshot.png");
    await flush();

    expect(document.getElementById("upload-error").textContent).toContain("next stage");
    expect(inspectCalls(fetchMock)).toHaveLength(0);
  });

  it("runs one correlated upload and renders the decoded structure without fabricating a prompt", async () => {
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
    expect(inspect[0][0]).toMatch(/^\/api\/inspect\?upload_attempt_id=[A-Za-z0-9-]+$/);
    expect(inspect[0][1].method).toBe("POST");
    expect(inspect[0][1].body).toBeInstanceOf(FormData);
    expect(inspect[0][1].headers?.["Content-Type"]).toBeUndefined();

    expect(document.getElementById("screen-results").classList.contains("hidden")).toBe(false);
    expect(document.getElementById("res-title").textContent).toBe("clip.mp4");
    expect(document.querySelectorAll("#res-scenes .scene")).toHaveLength(1);
    expect(document.querySelector(".prompt-card").classList.contains("unavailable")).toBe(true);
    expect(document.querySelector(".unavailable-note").textContent).toContain("no prompt is fabricated");
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

    document.getElementById("again-btn").click();
    expect(document.getElementById("screen-home").classList.contains("hidden")).toBe(false);
    expect(document.getElementById("file-input").value).toBe("");
  });
});
