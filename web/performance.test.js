import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createActionTiming } from "./performance.js";

describe("content-free frontend action timings", () => {
  let now;
  beforeEach(() => {
    now = 100;
    sessionStorage.clear();
    vi.stubEnv("DEV", true);
    vi.spyOn(performance, "now").mockImplementation(() => now);
    vi.spyOn(console, "info").mockImplementation(() => {});
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("uses monotonic times for readiness, upload, polling and click-to-result", () => {
    const timing = createActionTiming("decode_video");
    now = 110; timing.mark("readability_complete");
    now = 130; timing.mark("readiness_complete");
    now = 140; timing.mark("upload_start");
    now = 240; timing.mark("upload_returned");
    now = 245; timing.mark("job_available");
    timing.add("poll_requests"); timing.add("poll_request_ms", 25);
    timing.add("poll_wait_ms", 1500);
    now = 1790; timing.mark("result_detected");
    now = 1800; timing.mark("result_received");
    now = 1805; timing.mark("result_displayed"); timing.finish(); timing.finish();
    expect(console.info).toHaveBeenCalledTimes(1);
    const [event, values] = console.info.mock.calls[0];
    expect(event).toBe("orb_perf_frontend");
    expect(values).toMatchObject({ operation: "decode_video", status: "complete", total_ms: 1705,
      readiness_wait_ms: 20, upload_request_ms: 100, job_available_ms: 145,
      poll_requests: 1, poll_wait_ms: 1500, poll_request_ms: 25 });
  });

  it.each(["decode_image", "compose_image", "compose_video", "enhance"])("handles %s without content", (operation) => {
    const timing = createActionTiming(operation);
    timing.mark("prompt:private content"); timing.add("wallet", 32); timing.add("poll_wait_ms", NaN);
    now = 150; timing.finish("private prompt");
    expect(console.info.mock.calls[0][1]).toEqual({ operation, status: "error", total_ms: 50 });
  });

  it("does not log by default in production", () => {
    vi.stubEnv("DEV", false);
    expect(createActionTiming("enhance")).toBeNull();
    expect(console.info).not.toHaveBeenCalled();
  });

  it("allows an explicit local browser production opt-in", () => {
    vi.stubEnv("DEV", false);
    sessionStorage.setItem("orb-perf", "1");
    createActionTiming("enhance").finish();
    expect(console.info).toHaveBeenCalledTimes(1);
  });

  it("records startup readiness separately from the clicked AI operation", () => {
    const timing = createActionTiming("service_startup");
    now = 10100; timing.mark("readiness_complete"); timing.finish();
    expect(console.info).toHaveBeenCalledWith("orb_perf_service", expect.objectContaining({
      operation: "service_startup", readiness_wait_ms: 10000, total_ms: 10000,
    }));
  });

  it("logging failure does not escape into the application", () => {
    console.info.mockImplementation(() => { throw new Error("console unavailable"); });
    const timing = createActionTiming("compose_image");
    expect(() => timing.finish()).not.toThrow();
  });
});
