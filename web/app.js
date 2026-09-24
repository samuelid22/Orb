"use strict";

import { apiUrl } from "./api-url.js";

const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;
const REQUEST_TIMEOUT_MS = 15000;
const UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;
const SERVICE_RETRY_MS = 2000;
const SERVICE_DEADLINE_MS = 100000;
const DECODE_STEPS = [
  { id: "uploading", label: "Uploading" },
  { id: "structure", label: "Reading structure" },
  { id: "scenes", label: "Detecting scenes" },
  { id: "results", label: "Preparing results" },
];

const screens = {
  home: document.getElementById("screen-home"),
  processing: document.getElementById("screen-processing"),
  results: document.getElementById("screen-results"),
};

const els = {
  fileInput: document.getElementById("file-input"),
  dropzone: document.getElementById("dropzone"),
  fileCard: document.getElementById("file-card"),
  fileName: document.getElementById("file-name"),
  fileMeta: document.getElementById("file-meta"),
  fileClear: document.getElementById("file-clear"),
  serviceStatus: document.getElementById("service-status"),
  decodeBtn: document.getElementById("decode-btn"),
  uploadError: document.getElementById("upload-error"),
  phaseText: document.getElementById("phase-text"),
  phaseDetail: document.getElementById("phase-detail"),
  uploadBar: document.getElementById("upload-bar"),
  uploadProgress: document.querySelector(".progress"),
  stepList: document.getElementById("step-list"),
  jobError: document.getElementById("job-error"),
  backBtn: document.getElementById("back-btn"),
  resTitle: document.getElementById("res-title"),
  resChips: document.getElementById("res-chips"),
  resVideo: document.getElementById("res-video"),
  resSummary: document.getElementById("res-summary"),
  resScenes: document.getElementById("res-scenes"),
  againBtn: document.getElementById("again-btn"),
};

const decodeLabel = els.decodeBtn.querySelector("span");
const decodeDetail = els.decodeBtn.querySelector("small");

let selectedFile = null;
let serviceReady = false;
let serviceTask = null;
let actionBusy = false;
let pollTimer = null;
let pollFailures = 0;
let currentJobId = null;

function showScreen(name) {
  for (const key of Object.keys(screens)) {
    screens[key].classList.toggle("hidden", key !== name);
  }
  window.scrollTo(0, 0);
  screens[name].focus({ preventScroll: true });
}

function showError(box, message) {
  box.textContent = message;
  box.classList.remove("hidden");
}

async function fetchWithTimeout(url, options = {}, timeout = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function createUploadAttemptId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `orb-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function uploadAttemptUrl(endpoint, attemptId) {
  const separator = endpoint.includes("?") ? "&" : "?";
  return apiUrl(`${endpoint}${separator}upload_attempt_id=${encodeURIComponent(attemptId)}`);
}

function setServiceState(ready) {
  serviceReady = ready;
  els.decodeBtn.classList.toggle("initializing", !ready);
  decodeLabel.textContent = ready ? "Decode video" : "Initializing";
  decodeDetail.textContent = ready ? "Run the free structural analysis" : "Orb service waking up";
  syncDecodeButton();
}

function syncDecodeButton() {
  els.decodeBtn.disabled = !selectedFile || !serviceReady || actionBusy;
}

/* ---------- Service readiness (health -> ready -> upload-path canary) ---------- */

async function pingUploadPath() {
  const pingId = createUploadAttemptId();
  const form = new FormData();
  form.append(
    "file",
    new Blob(["orb-upload-ping"], { type: "application/octet-stream" }),
    "ping.bin",
  );
  const response = await fetchWithTimeout(
    apiUrl(`/api/upload-ping?upload_ping_id=${encodeURIComponent(pingId)}`),
    { method: "POST", body: form },
  );
  if (response.status === 204) return "ok";
  if (response.status === 404 || response.status === 405) return "unsupported";
  return "fail";
}

async function waitForService() {
  if (serviceReady) return true;
  if (serviceTask) return serviceTask;

  serviceTask = (async () => {
    const deadline = Date.now() + SERVICE_DEADLINE_MS;
    while (Date.now() < deadline) {
      try {
        const health = await fetchWithTimeout(apiUrl("/api/health"));
        const healthBody = await health.json().catch(() => ({}));
        if (health.ok && healthBody.status === "ok") {
          const ready = await fetchWithTimeout(apiUrl("/api/ready"));
          const readyBody = await ready.json().catch(() => ({}));
          if (ready.ok && readyBody.status === "ready") {
            const ping = await pingUploadPath();
            if (ping === "ok" || ping === "unsupported") {
              els.serviceStatus.textContent = "Orb service ready.";
              els.serviceStatus.classList.add("ready");
              setServiceState(true);
              return true;
            }
            els.serviceStatus.textContent = "Upload service is reconnecting…";
          }
        }
      } catch (error) {
        // The service may still be starting; retry until the deadline.
      }
      if (Date.now() < deadline) {
        await delay(Math.min(SERVICE_RETRY_MS, deadline - Date.now()));
      }
    }
    setServiceState(false);
    els.serviceStatus.textContent = "The Orb service did not become ready. Check the backend and try again.";
    return false;
  })();

  try {
    return await serviceTask;
  } finally {
    serviceTask = null;
  }
}

async function isServiceReady() {
  if (!serviceReady) return false;
  try {
    const ready = await fetchWithTimeout(apiUrl("/api/ready"));
    const body = await ready.json().catch(() => ({}));
    if (ready.ok && body.status === "ready") return true;
  } catch (error) {
    // Only decides whether a new upload may begin.
  }
  setServiceState(false);
  void waitForService();
  return false;
}

/* ---------- File selection ---------- */

function setFile(file) {
  if (!file) return;
  if (/\.(png|jpe?g|gif|webp|bmp|avif|heic)$/i.test(file.name)) {
    showError(els.uploadError, "Image decoding arrives in the next stage. Upload a video to decode its structure now.");
    return;
  }
  if (!/\.(mp4|m4v|mov|webm)$/i.test(file.name)) {
    showError(els.uploadError, "Unsupported file type. Upload an MP4, MOV, or WebM video.");
    return;
  }
  if (file.size === 0) {
    showError(els.uploadError, "That file is empty. Choose a different video.");
    return;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    showError(els.uploadError, "That video exceeds the 200 MB limit. Choose a smaller file.");
    return;
  }
  selectedFile = file;
  els.uploadError.classList.add("hidden");
  els.dropzone.classList.add("hidden");
  els.fileCard.classList.remove("hidden");
  els.fileName.textContent = file.name;
  els.fileMeta.textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB`;
  syncDecodeButton();
}

function clearFile() {
  selectedFile = null;
  els.fileInput.value = "";
  els.fileCard.classList.add("hidden");
  els.dropzone.classList.remove("hidden");
  syncDecodeButton();
}

/* ---------- Decode flow ---------- */

function mapStage(stage) {
  if (!stage || stage === "Queued") return { step: "uploading", detail: "Waiting for the engine" };
  if (stage === "Inspecting video") return { step: "structure", detail: "Reading video metadata" };
  if (stage === "Detecting scene cuts") return { step: "scenes", detail: "Measuring scene changes" };
  if (stage === "Complete") return { step: "results", detail: "Preparing results" };
  return { step: "scenes", detail: stage };
}

function renderSteps(activeStep, uploadDone) {
  const order = DECODE_STEPS.map((s) => s.id);
  const activeIndex = order.indexOf(activeStep);
  els.stepList.innerHTML = "";
  DECODE_STEPS.forEach((step, index) => {
    const li = document.createElement("li");
    let state = "pending";
    if (index < activeIndex || (uploadDone && activeStep === "results")) state = "done";
    if (step.id === activeStep) state = "active";
    li.className = `step-state-${state}`;
    li.innerHTML = `<span class="dot"></span>${step.label}`;
    els.stepList.appendChild(li);
  });
}

async function startDecode() {
  if (!selectedFile || actionBusy || !serviceReady) return;
  actionBusy = true;
  syncDecodeButton();
  if (!await isServiceReady()) {
    actionBusy = false;
    syncDecodeButton();
    return;
  }

  clearTimeout(pollTimer);
  currentJobId = null;
  els.uploadError.classList.add("hidden");
  els.decodeBtn.disabled = true;
  showScreen("processing");
  els.jobError.classList.add("hidden");
  els.backBtn.classList.add("hidden");
  els.uploadBar.style.width = "";
  els.uploadProgress.classList.add("is-indeterminate");
  els.uploadProgress.removeAttribute("aria-valuenow");
  renderSteps("uploading", false);
  els.phaseText.textContent = "Uploading video";
  els.phaseDetail.textContent = "Sending the file to the Orb engine";

  const attemptId = createUploadAttemptId();
  const fail = (message) => {
    actionBusy = false;
    els.uploadProgress.classList.remove("is-indeterminate");
    showError(els.jobError, message);
    els.backBtn.classList.remove("hidden");
    syncDecodeButton();
  };

  // Reliability pre-check: prove the first bytes are readable before the
  // body is streamed. A pass does not guarantee the whole file uploads.
  let precheck = "skipped";
  let precheckErrorName = "";
  try {
    const probe = selectedFile.slice(0, 64 * 1024);
    if (typeof probe.arrayBuffer === "function") {
      await probe.arrayBuffer();
      precheck = "readable";
    }
  } catch (error) {
    precheck = "unreadable";
    precheckErrorName = error?.name || "UnknownError";
  }
  console.info(`upload_attempt=${attemptId} precheck=${precheck}`);
  if (precheck === "unreadable") {
    const reason = precheckErrorName === "NotReadableError" || precheckErrorName === "NotFoundError"
      ? "This video couldn't be accessed through the selected source. Please select it again using Files or Browse instead of Gallery."
      : "The selected video could not be read from this device before upload.";
    fail(`${reason} (${precheckErrorName}) No upload was started and no retry was made. Reference: ${attemptId}.`);
    return;
  }

  const form = new FormData();
  form.append("file", selectedFile);
  let response;
  try {
    // No Content-Type header keeps this FormData POST a simple CORS request.
    response = await fetchWithTimeout(
      uploadAttemptUrl("/api/inspect", attemptId),
      { method: "POST", body: form },
      UPLOAD_TIMEOUT_MS,
    );
  } catch (error) {
    const timedOut = error?.name === "AbortError";
    fail(
      timedOut
        ? `Upload timed out before Orb returned a response. No retry was made. Reference: ${attemptId}.`
        : `Upload connection was interrupted before Orb returned a response. No retry was made. Reference: ${attemptId}.`,
    );
    return;
  }

  els.uploadProgress.classList.remove("is-indeterminate");
  els.uploadBar.style.width = "100%";
  els.uploadProgress.setAttribute("aria-valuenow", "100");
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.job_id) {
    fail(`Could not start decoding: ${data.detail || `upload failed (${response.status})`}`);
    return;
  }
  currentJobId = data.job_id;
  selectedFile = null;
  actionBusy = false;
  clearFile();
  startPolling(currentJobId);
}

/* ---------- Job polling and results ---------- */

function startPolling(jobId) {
  clearTimeout(pollTimer);
  pollFailures = 0;
  showScreen("processing");
  els.jobError.classList.add("hidden");
  els.backBtn.classList.add("hidden");
  pollJob(jobId);
}

function schedulePoll(jobId, ms = 1500) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(() => pollJob(jobId), ms);
}

async function pollJob(jobId) {
  if (jobId !== currentJobId) return;
  let job;
  try {
    const response = await fetchWithTimeout(apiUrl(`/api/jobs/${jobId}`));
    if (response.status === 404 || response.status === 410) {
      discardJob();
      return;
    }
    if (!response.ok) throw new Error(`Server returned ${response.status}.`);
    job = await response.json();
  } catch (error) {
    pollFailures += 1;
    if (pollFailures < 3 && currentJobId === jobId) {
      schedulePoll(jobId, 1500 * pollFailures);
      return;
    }
    showError(els.jobError, `Connection interrupted: ${error.message || "could not check decoding status"}`);
    els.backBtn.classList.remove("hidden");
    return;
  }
  pollFailures = 0;
  const mapped = mapStage(job.stage || "");
  els.phaseText.textContent = DECODE_STEPS.find((s) => s.id === mapped.step).label;
  els.phaseDetail.textContent = job.stage || "";
  renderSteps(mapped.step, true);
  if (job.state === "complete") {
    clearTimeout(pollTimer);
    fetchResult(jobId);
  } else if (job.state === "error") {
    clearTimeout(pollTimer);
    showError(els.jobError, `Analysis failed: ${job.error || "unknown error"}`);
    currentJobId = null;
    els.backBtn.classList.remove("hidden");
  } else {
    schedulePoll(jobId);
  }
}

function discardJob() {
  clearTimeout(pollTimer);
  currentJobId = null;
  clearFile();
  showScreen("home");
  showError(els.uploadError, "This analysis is no longer available on the server.");
}

async function fetchResult(jobId) {
  try {
    const response = await fetchWithTimeout(apiUrl(`/api/jobs/${jobId}/result`));
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `status ${response.status}`);
    renderResult(result);
  } catch (error) {
    showError(els.jobError, `Could not load results: ${error.message}`);
    els.backBtn.classList.remove("hidden");
  }
}

function fmtTime(seconds) {
  return `${Number(seconds).toFixed(1)}s`;
}

function renderResult(result) {
  const video = result.video || {};
  els.resTitle.textContent = video.name || "Decoded video";
  els.resChips.innerHTML = "";
  const chips = [
    video.width && video.height ? `${video.width}×${video.height}` : null,
    video.duration ? `${video.duration.toFixed(1)}s` : null,
    video.fps ? `${video.fps} fps` : null,
    result.scenes ? `${result.scenes.length} scenes` : null,
  ].filter(Boolean);
  for (const chip of chips) {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = chip;
    els.resChips.appendChild(span);
  }

  if (video.preview_url) {
    els.resVideo.src = apiUrl(video.preview_url);
    els.resVideo.classList.remove("hidden");
  } else {
    els.resVideo.classList.add("hidden");
  }

  els.resSummary.textContent = result.summary || "";

  els.resScenes.innerHTML = "";
  for (const scene of result.scenes || []) {
    const card = document.createElement("div");
    card.className = "scene";
    const thumb = scene.frames && scene.frames.length ? apiUrl(scene.frames[0]) : "";
    card.innerHTML = `
      ${thumb ? `<img loading="lazy" src="${thumb}" alt="Scene ${scene.index} thumbnail">` : ""}
      <div class="scene-meta">
        <strong>Scene ${scene.index}</strong>
        ${fmtTime(scene.start)} – ${fmtTime(scene.end)} &middot; ${Number(scene.duration).toFixed(1)}s
      </div>`;
    els.resScenes.appendChild(card);
  }

  showScreen("results");
}

/* ---------- Wiring ---------- */

els.dropzone.addEventListener("click", (event) => {
  if (event.target !== els.fileInput) els.fileInput.click();
});
els.dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    els.fileInput.click();
  }
});
["dragover", "dragenter"].forEach((name) =>
  els.dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    els.dropzone.classList.add("dragover");
  }),
);
["dragleave", "drop"].forEach((name) =>
  els.dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    els.dropzone.classList.remove("dragover");
  }),
);
els.dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) setFile(file);
});
els.fileInput.addEventListener("change", () => {
  if (els.fileInput.files && els.fileInput.files[0]) setFile(els.fileInput.files[0]);
});
els.fileClear.addEventListener("click", clearFile);
els.decodeBtn.addEventListener("click", startDecode);
els.backBtn.addEventListener("click", () => {
  syncDecodeButton();
  showScreen("home");
});
els.againBtn.addEventListener("click", () => {
  clearTimeout(pollTimer);
  currentJobId = null;
  clearFile();
  showScreen("home");
});

window.addEventListener("focus", () => {
  if (!serviceReady) void waitForService();
});
window.addEventListener("online", () => {
  if (!serviceReady) void waitForService();
});

setServiceState(false);
showScreen("home");
void waitForService();
