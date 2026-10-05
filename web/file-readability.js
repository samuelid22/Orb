// Read only a small prefix. Local retries never submit an upload or AI job.
export const FILE_READ_TIMEOUT_MS = 5000;
export const FILE_READ_RETRY_DELAYS_MS = [300, 800];
const FILE_READ_BYTES = 64 * 1024;

function abortError() {
  return new DOMException("File check cancelled", "AbortError");
}

function readHead(file, signal) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let reader;
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      if (reader?.readyState === 1) reader.abort();
      if (error) reject(error);
      else resolve();
    };
    const onAbort = () => finish(abortError());
    const timer = setTimeout(() => finish(new DOMException("File check timed out", "TimeoutError")), FILE_READ_TIMEOUT_MS);
    signal?.addEventListener("abort", onAbort, { once: true });
    if (signal?.aborted) return onAbort();
    try {
      const head = file.slice(0, FILE_READ_BYTES);
      if (typeof head.arrayBuffer === "function") {
        Promise.resolve(head.arrayBuffer()).then(() => finish(), finish);
      } else {
        reader = new FileReader();
        reader.onload = () => finish();
        reader.onerror = () => finish(reader.error || new DOMException("File unreadable", "NotReadableError"));
        reader.onabort = () => finish(abortError());
        reader.readAsArrayBuffer(head);
      }
    } catch (error) {
      finish(error);
    }
  });
}

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
    if (signal?.aborted) onAbort();
  });
}

export async function checkFileReadable(file, { signal } = {}) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      await readHead(file, signal);
      return;
    } catch (error) {
      if (signal?.aborted) throw abortError();
      if (!["NotReadableError", "NotFoundError"].includes(error?.name)
          || attempt >= FILE_READ_RETRY_DELAYS_MS.length) throw error;
      await delay(FILE_READ_RETRY_DELAYS_MS[attempt], signal);
    }
  }
}
