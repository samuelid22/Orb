import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { checkFileReadable, FILE_READ_TIMEOUT_MS } from "./file-readability.js";

describe("local file readability", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.restoreAllMocks(); });

  function file(read) { return { slice: vi.fn(() => ({ arrayBuffer: read })) }; }

  it("reads only the first 64 KB once on success", async () => {
    const read = vi.fn().mockResolvedValue(new ArrayBuffer(8));
    const selected = file(read);
    await checkFileReadable(selected);
    expect(selected.slice).toHaveBeenCalledExactlyOnceWith(0, 64 * 1024);
    expect(read).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each(["NotReadableError", "NotFoundError"])("retries %s at 300 ms and 800 ms, then stops", async (name) => {
    const error = new DOMException("unavailable", name);
    const read = vi.fn().mockRejectedValue(error);
    const result = checkFileReadable(file(read)).catch((failure) => failure);
    await vi.advanceTimersByTimeAsync(299);
    expect(read).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(read).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(799);
    expect(read).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(read).toHaveBeenCalledTimes(3);
    expect(await result).toBe(error);
    await vi.advanceTimersByTimeAsync(20000);
    expect(read).toHaveBeenCalledTimes(3);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("succeeds on the third read without any further attempts", async () => {
    const read = vi.fn().mockRejectedValueOnce(new DOMException("missing", "NotFoundError"))
      .mockRejectedValueOnce(new DOMException("locked", "NotReadableError"))
      .mockResolvedValue(new ArrayBuffer(8));
    const result = checkFileReadable(file(read));
    await vi.advanceTimersByTimeAsync(1100);
    await result;
    expect(read).toHaveBeenCalledTimes(3);
  });

  it("does not retry other errors", async () => {
    const read = vi.fn().mockRejectedValue(new DOMException("denied", "SecurityError"));
    await expect(checkFileReadable(file(read))).rejects.toMatchObject({ name: "SecurityError" });
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("times out without retrying and ignores late success", async () => {
    let resolve;
    const read = vi.fn(() => new Promise((done) => { resolve = done; }));
    const result = checkFileReadable(file(read)).catch((failure) => failure);
    await vi.advanceTimersByTimeAsync(FILE_READ_TIMEOUT_MS);
    expect(await result).toMatchObject({ name: "TimeoutError" });
    resolve(new ArrayBuffer(8));
    await vi.advanceTimersByTimeAsync(10000);
    expect(read).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancels pending reads and ignores late resolution", async () => {
    const controller = new AbortController();
    let resolve;
    const read = vi.fn(() => new Promise((done) => { resolve = done; }));
    const result = checkFileReadable(file(read), { signal: controller.signal }).catch((failure) => failure);
    controller.abort();
    expect(await result).toMatchObject({ name: "AbortError" });
    resolve(new ArrayBuffer(8));
    await vi.advanceTimersByTimeAsync(10000);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("cancels a retry delay without reading again", async () => {
    const controller = new AbortController();
    const read = vi.fn().mockRejectedValue(new DOMException("locked", "NotReadableError"));
    const result = checkFileReadable(file(read), { signal: controller.signal }).catch((failure) => failure);
    await vi.advanceTimersByTimeAsync(100);
    controller.abort();
    expect(await result).toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(10000);
    expect(read).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("uses a small FileReader read when arrayBuffer is unavailable", async () => {
    vi.useRealTimers();
    const selected = new File(["readable"], "clip.mp4");
    const slice = vi.spyOn(selected, "slice");
    await checkFileReadable(selected);
    expect(slice).toHaveBeenCalledExactlyOnceWith(0, 64 * 1024);
  });
});
