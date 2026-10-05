// Content-free browser diagnostics. Production is quiet unless locally opted in
// with sessionStorage.setItem("orb-perf", "1"); no server configuration needed.
const MARKS = new Set(["readability_complete", "readiness_complete", "upload_start", "upload_returned",
  "job_available", "result_detected", "result_received", "result_displayed"]);
const COUNTERS = new Set(["poll_requests", "poll_request_ms", "poll_wait_ms"]);

export function createActionTiming(operation) {
  let enabled = Boolean(import.meta.env.DEV);
  try { enabled ||= sessionStorage.getItem("orb-perf") === "1"; } catch { /* Storage may be disabled. */ }
  if (!enabled || !["decode_image", "decode_video", "compose_image", "compose_video", "enhance", "service_startup"].includes(operation)) return null;
  const started = performance.now();
  const metrics = {};
  let finished = false;
  function safe(callback) { try { callback(); } catch { /* Diagnostics never affect the UI. */ } }
  return {
    mark(name) { safe(() => {
      if (MARKS.has(name) && metrics[name + "_ms"] === undefined) metrics[name + "_ms"] = performance.now() - started;
    }); },
    add(name, value = 1) { safe(() => {
      if (COUNTERS.has(name) && Number.isFinite(value) && value >= 0) metrics[name] = (metrics[name] || 0) + value;
    }); },
    finish(status = "complete") { safe(() => {
      if (finished) return;
      finished = true;
      const end = performance.now();
      const values = { ...metrics, total_ms: end - started };
      if (values.upload_start_ms !== undefined && values.upload_returned_ms !== undefined) {
        values.upload_request_ms = values.upload_returned_ms - values.upload_start_ms;
      }
      if (values.readability_complete_ms !== undefined && values.readiness_complete_ms !== undefined) {
        values.readiness_wait_ms = values.readiness_complete_ms - values.readability_complete_ms;
      } else if (values.readiness_complete_ms !== undefined) values.readiness_wait_ms = values.readiness_complete_ms;
      console.info(operation === "service_startup" ? "orb_perf_service" : "orb_perf_frontend", { operation, status: ["complete", "error", "cancelled"].includes(status) ? status : "error",
        ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, Math.round(value * 1000) / 1000])) });
    }); },
  };
}
