// Health probes are cheap; full readiness/upload verification retains its own
// longer timeout and cooldown. There is only one awaited request at a time.
const HEALTH_TIMEOUT_MS = 5000;
const VERIFY_TIMEOUT_MS = 15000;
const HEALTH_RETRY_MS = 1000;
const VERIFY_RETRY_MS = 5000;
const RECOVERY_DEADLINE_MS = 100000;

export async function recoverService({ probeHealth, onHealth, verifyReadiness }) {
  const deadline = performance.now() + RECOVERY_DEADLINE_MS;
  const remaining = () => Math.max(0, deadline - performance.now());

  async function request(task, timeout = VERIFY_TIMEOUT_MS) {
    if (!remaining()) throw new Error("Service recovery deadline reached");
    const controller = new AbortController();
    let timer;
    try {
      const expired = new Promise((_, reject) => {
        timer = setTimeout(() => {
          // Reject even if an implementation ignores abort. Late completion
          // cannot resume this attempt or change application readiness.
          reject(new Error("Service check timed out"));
          controller.abort();
        }, Math.min(timeout, remaining()));
      });
      const result = await Promise.race([task(controller.signal), expired]);
      if (!remaining()) throw new Error("Service recovery deadline reached");
      return result;
    } finally {
      clearTimeout(timer);
    }
  }

  while (remaining()) {
    let retryDelay = HEALTH_RETRY_MS;
    try {
      const health = await request(probeHealth, HEALTH_TIMEOUT_MS);
      if (health) {
        if (onHealth(health) === false) return false;
        retryDelay = VERIFY_RETRY_MS;
        if (await verifyReadiness(request)) return true;
      }
    } catch {
      // Network latency/failures do not consume an attempt budget. Keep the
      // entire recovery window available, with bounded sequential requests.
    }
    if (remaining()) {
      await new Promise((resolve) => setTimeout(resolve, Math.min(retryDelay, remaining())));
    }
  }
  return false;
}
