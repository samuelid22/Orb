import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { recoverService } from "./service-recovery.js";

describe("backend wake-up recovery", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });

  function checks(overrides = {}) {
    const probeHealth = vi.fn().mockResolvedValue({ status: "ok" });
    const onHealth = vi.fn();
    const ready = vi.fn().mockResolvedValue(true);
    const canary = vi.fn().mockResolvedValue(true);
    const verifyReadiness = vi.fn(async (request) => {
      if (!await request(ready)) return false;
      return request(canary);
    });
    return { probeHealth, onHealth, ready, canary, verifyReadiness, ...overrides };
  }

  it("checks an awake backend immediately, verifies both paths once, then stops", async () => {
    const c = checks();
    expect(await recoverService(c)).toBe(true);
    await vi.advanceTimersByTimeAsync(120000);
    expect(c.probeHealth).toHaveBeenCalledTimes(1);
    expect(c.ready).toHaveBeenCalledTimes(1);
    expect(c.canary).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([5000, 20000, 60000])("recognizes a backend waking at %i ms within one second", async (wakeAt) => {
    const start = performance.now();
    const c = checks({ probeHealth: vi.fn(async () => performance.now() - start >= wakeAt ? { status: "ok" } : null) });
    const result = recoverService(c);
    await vi.advanceTimersByTimeAsync(wakeAt - 1);
    expect(c.ready).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(await result).toBe(true);
    expect(c.probeHealth).toHaveBeenCalledTimes(wakeAt / 1000 + 1);
    expect(c.canary).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("aborts a health request at five seconds and pauses one second before retrying", async () => {
    let signal;
    const c = checks();
    c.probeHealth.mockImplementationOnce((s) => { signal = s; return new Promise(() => {}); });
    const result = recoverService(c);
    await vi.advanceTimersByTimeAsync(4999);
    expect(signal.aborted).toBe(false);
    expect(c.probeHealth).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(999);
    expect(c.probeHealth).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(await result).toBe(true);
    expect(c.probeHealth).toHaveBeenCalledTimes(2);
  });

  it("recovers from intermittent network failures without shortening the window", async () => {
    const c = checks();
    c.probeHealth.mockRejectedValueOnce(new TypeError("Network error"))
      .mockResolvedValueOnce(null).mockRejectedValueOnce(new TypeError("Network error"));
    const result = recoverService(c);
    await vi.advanceTimersByTimeAsync(3000);
    expect(await result).toBe(true);
    expect(c.probeHealth).toHaveBeenCalledTimes(4);
    expect(c.canary).toHaveBeenCalledTimes(1);
  });

  it("waits one second after each failed response completes, never overlapping probes", async () => {
    let active = 0;
    let peak = 0;
    const starts = [];
    const start = performance.now();
    const c = checks({ probeHealth: vi.fn(async () => {
      starts.push(performance.now() - start);
      peak = Math.max(peak, ++active);
      await new Promise((resolve) => setTimeout(resolve, 2000));
      active--;
      return starts.length === 3 ? { status: "ok" } : null;
    }) });
    const result = recoverService(c);
    await vi.advanceTimersByTimeAsync(8000);
    expect(await result).toBe(true);
    expect(starts).toEqual([0, 3000, 6000]);
    expect(peak).toBe(1);
  });

  it.each(["ready", "canary"])("preserves the full 15-second %s timeout and spaces failed verification by five seconds", async (stage) => {
    const c = checks();
    let signal;
    c[stage].mockImplementationOnce((s) => { signal = s; return new Promise(() => {}); });
    const result = recoverService(c);
    await vi.advanceTimersByTimeAsync(14999);
    expect(signal.aborted).toBe(false);
    expect(c.probeHealth).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(4999);
    expect(c.probeHealth).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(await result).toBe(true);
    expect(c[stage]).toHaveBeenCalledTimes(2);
    expect(c.canary).toHaveBeenCalledTimes(stage === "ready" ? 1 : 2);
  });

  it.each(["ready", "canary"])("requires successful %s verification and does not repeat it every second", async (stage) => {
    const c = checks();
    c[stage].mockResolvedValueOnce(false);
    const result = recoverService(c);
    await vi.advanceTimersByTimeAsync(4999);
    expect(c[stage]).toHaveBeenCalledTimes(1);
    expect(c.canary).toHaveBeenCalledTimes(stage === "ready" ? 0 : 1);
    await vi.advanceTimersByTimeAsync(1);
    expect(await result).toBe(true);
    expect(c.canary).toHaveBeenCalledTimes(stage === "ready" ? 1 : 2);
  });

  it("ignores late success from an aborted health probe after recovery", async () => {
    let resolveOld;
    const c = checks();
    c.probeHealth.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    const result = recoverService(c);
    await vi.advanceTimersByTimeAsync(6000);
    expect(await result).toBe(true);
    resolveOld({ status: "ok", orb_ai_access: "configuration_required" });
    await vi.advanceTimersByTimeAsync(120000);
    expect(c.onHealth).toHaveBeenCalledTimes(1);
    expect(c.onHealth).toHaveBeenCalledWith({ status: "ok" });
    expect(c.canary).toHaveBeenCalledTimes(1);
    expect(c.probeHealth).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each(["fast failures", "timeouts"])("uses the entire 100-second window for %s with bounded load", async (kind) => {
    const c = checks({ probeHealth: vi.fn(kind === "timeouts" ? () => new Promise(() => {}) : async () => null) });
    let outcome;
    const result = recoverService(c).then((value) => { outcome = value; });
    await vi.advanceTimersByTimeAsync(99999);
    expect(outcome).toBeUndefined();
    await vi.advanceTimersByTimeAsync(1);
    await result;
    expect(outcome).toBe(false);
    expect(c.probeHealth).toHaveBeenCalledTimes(kind === "timeouts" ? 17 : 100);
    expect(c.ready).not.toHaveBeenCalled();
    expect(c.canary).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("bounds full verification by the remaining deadline, ignoring late canary completion", async () => {
    const c = checks();
    const start = performance.now();
    c.probeHealth.mockImplementation(async () => performance.now() - start >= 95000 ? { status: "ok" } : null);
    let resolveCanary;
    let signal;
    c.canary.mockImplementation((s) => { signal = s; return new Promise((resolve) => { resolveCanary = resolve; }); });
    const result = recoverService(c);
    await vi.advanceTimersByTimeAsync(100000);
    expect(await result).toBe(false);
    expect(signal.aborted).toBe(true);
    resolveCanary(true);
    await vi.advanceTimersByTimeAsync(15000);
    expect(c.canary).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("preserves terminal configuration-unavailable handling without running a canary", async () => {
    const c = checks({ onHealth: vi.fn(() => false) });
    expect(await recoverService(c)).toBe(false);
    expect(c.ready).not.toHaveBeenCalled();
    expect(c.canary).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
