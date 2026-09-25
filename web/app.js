"use strict";

import { apiUrl } from "./api-url.js";
import { initWallet } from "./wallet.js";

const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const REQUEST_TIMEOUT_MS = 15000;
const UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;
const SERVICE_RETRY_MS = 2000;
const SERVICE_DEADLINE_MS = 100000;
const STEP_LABELS = {
  video: ["Uploading", "Reading structure", "Analyzing scenes", "Preparing results"],
  image: ["Uploading", "Analyzing image", "Generating prompt", "Preparing results"],
  enhance: ["Starting", "Improving prompt", "Reviewing response", "Preparing results"],
};
const STEP_IDS = ["uploading", "structure", "scenes", "results"];
const ACTIVE_JOB_KEY = "orb-active-paid-job";

const screens = {
  home: document.getElementById("screen-home"),
  processing: document.getElementById("screen-processing"),
  results: document.getElementById("screen-results"),
};

const els = {
  fileInput: document.getElementById("file-input"),
  chooseFileBtn: document.getElementById("choose-file-btn"),
  uploadShell: document.getElementById("upload-shell"),
  dropzone: document.getElementById("dropzone"),
  fileCard: document.getElementById("file-card"),
  fileName: document.getElementById("file-name"),
  fileMeta: document.getElementById("file-meta"),
  fileClear: document.getElementById("file-clear"),
  serviceStatus: document.getElementById("service-status"),
  enhanceStatus: document.getElementById("enhance-status"),
  decodeBtn: document.getElementById("decode-btn"),
  fileKicker: document.getElementById("file-kicker"),
  modeDecode: document.getElementById("mode-decode"),
  modeCompose: document.getElementById("mode-compose"),
  modeEnhance: document.getElementById("mode-enhance"),
  enhanceShell: document.getElementById("enhance-shell"),
  promptInput: document.getElementById("prompt-input"),
  enhanceOutput: document.getElementById("enhance-output"),
  enhanceStyle: document.getElementById("enhance-style"),
  enhanceDetail: document.getElementById("enhance-detail"),
  enhanceBtn: document.getElementById("enhance-btn"),
  enhanceError: document.getElementById("enhance-error"),
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
  resImage: document.getElementById("res-image"),
  resPreviewCard: document.getElementById("res-preview-card"),
  resAnalysisCard: document.getElementById("res-analysis-card"),
  resAnalysis: document.getElementById("res-analysis"),
  resEyebrow: document.getElementById("res-eyebrow"),
  resMode: document.getElementById("res-mode"),
  resPromptHeading: document.getElementById("res-prompt-heading"),
  resNotice: document.getElementById("res-notice"),
  resOriginal: document.getElementById("res-original"),
  resOriginalText: document.getElementById("res-original-text"),
  resPrompt: document.getElementById("res-prompt"),
  copyPrompt: document.getElementById("copy-prompt"),
  copyStatus: document.getElementById("copy-status"),
  resRefinements: document.getElementById("res-refinements"),
  resSummary: document.getElementById("res-summary"),
  resScenes: document.getElementById("res-scenes"),
  againBtn: document.getElementById("again-btn"),
  menuToggle: document.getElementById("menu-toggle"),
  siteMenu: document.getElementById("site-menu"),
  menuHome: document.getElementById("menu-home"),
  menuAbout: document.getElementById("menu-about"),
  menuWallet: document.getElementById("menu-wallet"),
  aboutPanel: document.getElementById("about-panel"),
  aboutClose: document.getElementById("about-close"),
  uploadCreditsCta: document.getElementById("upload-credits-cta"),
  enhanceCreditsCta: document.getElementById("enhance-credits-cta"),
};

const decodeLabel = els.decodeBtn.querySelector("span");
const decodeDetail = els.decodeBtn.querySelector("small");

let selectedFile = null;
let currentMode = "decode";
let activeMediaKind = null;
let serviceReady = false;
let serviceTask = null;
let actionBusy = false;
let pollTimer = null;
let pollFailures = 0;
let currentJobId = null;
let visualAttemptKey = null;
let enhanceAttemptKey = null;
let creditMode = "local";
let wallet = null;
let privateMediaUrls = [];
wallet = initWallet({ onBalance: () => { syncDecodeButton(); resumePaidJob(); } });

function rememberPaidJob(jobId) {
  if (creditMode === "credits" && wallet.walletAddress()) {
    sessionStorage.setItem(ACTIVE_JOB_KEY, JSON.stringify({ jobId, wallet: wallet.walletAddress(),
      mode: currentMode, mediaKind: activeMediaKind }));
  }
}

function forgetPaidJob() { sessionStorage.removeItem(ACTIVE_JOB_KEY); }

function resumePaidJob() {
  if (creditMode !== "credits" || !wallet?.isAuthenticated() || currentJobId || actionBusy) return;
  try {
    const saved = JSON.parse(sessionStorage.getItem(ACTIVE_JOB_KEY) || "null");
    if (saved?.wallet?.toLowerCase() === wallet.walletAddress()?.toLowerCase()
        && /^[a-f0-9]{32}$/.test(saved.jobId)) {
      if (["decode", "compose", "enhance"].includes(saved.mode)) currentMode = saved.mode;
      if (["image", "video"].includes(saved.mediaKind)) activeMediaKind = saved.mediaKind;
      currentJobId = saved.jobId;
      actionBusy = true;
      startPolling(currentJobId);
    }
  } catch { forgetPaidJob(); }
}

function showScreen(name) {
  setMenuOpen(false);
  setAboutOpen(false);
  wallet.close();
  for (const key of Object.keys(screens)) {
    screens[key].classList.toggle("hidden", key !== name);
  }
  window.scrollTo(0, 0);
  screens[name].focus({ preventScroll: true });
}

function setMenuOpen(open) {
  if (open) setAboutOpen(false);
  if (open) wallet.close();
  els.siteMenu.classList.toggle("hidden", !open);
  els.menuToggle.setAttribute("aria-expanded", String(open));
  els.menuToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
}

function setAboutOpen(open, restoreFocus = false) {
  els.aboutPanel.classList.toggle("hidden", !open);
  if (open) els.aboutClose.focus();
  else if (restoreFocus) els.menuToggle.focus();
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
  decodeLabel.textContent = ready ? (currentMode === "compose" ? "Compose prompt" : "Decode reference") : "Initializing";
  decodeDetail.textContent = ready ? "Analyze with Orb AI" : "Orb service waking up";
  syncDecodeButton();
}

function syncEnhanceStatus() {
  els.enhanceStatus.textContent = els.serviceStatus.textContent;
  els.enhanceStatus.className = els.serviceStatus.className;
}

function syncDecodeButton() {
  const needsCredits = creditMode === "credits" && !wallet?.hasCredit();
  if (creditMode === "credits" && serviceReady) {
    els.serviceStatus.textContent = needsCredits
      ? "Orb service ready. Connect a wallet or buy testnet credits to use AI."
      : "Orb service ready. Testnet credit available.";
    syncEnhanceStatus();
  }
  els.decodeBtn.disabled = !selectedFile || !serviceReady || actionBusy || needsCredits;
  els.enhanceBtn.disabled = els.promptInput.value.trim().length < 3 || !serviceReady || actionBusy || needsCredits;
  els.uploadCreditsCta.classList.toggle("hidden", creditMode !== "credits" || !needsCredits);
  els.enhanceCreditsCta.classList.toggle("hidden", creditMode !== "credits" || !needsCredits);
  els.menuHome.disabled = actionBusy;
  for (const button of [els.modeDecode, els.modeCompose, els.modeEnhance]) button.disabled = actionBusy;
}

function setMode(mode) {
  if (actionBusy || !["decode", "compose", "enhance"].includes(mode)) return;
  currentMode = mode;
  activeMediaKind = null;
  clearFile();
  els.uploadError.classList.add("hidden");
  els.enhanceError.classList.add("hidden");
  els.uploadShell.classList.toggle("hidden", mode === "enhance");
  els.enhanceShell.classList.toggle("hidden", mode !== "enhance");
  for (const name of ["decode", "compose", "enhance"]) {
    const button = els[`mode${name[0].toUpperCase()}${name.slice(1)}`];
    button.classList.toggle("active", name === mode);
    if (name === mode) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  els.fileKicker.textContent = mode === "compose" ? "Ready to compose" : "Ready to decode";
  setServiceState(serviceReady);
  syncEnhanceStatus();
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
          creditMode = healthBody.orb_ai_access || "local";
          syncDecodeButton();
          resumePaidJob();
          if (healthBody.orb_ai_access === "configuration_required" || healthBody.orb_ai_access === "credits_unavailable") {
            setServiceState(false);
            els.serviceStatus.textContent = healthBody.orb_ai_access === "configuration_required"
              ? "Orb AI needs a server-side provider key and local testing configuration."
              : "AI operations are paused until verified credits are available.";
            els.serviceStatus.classList.add("failed");
            syncEnhanceStatus();
            return false;
          }
          const ready = await fetchWithTimeout(apiUrl("/api/ready"));
          const readyBody = await ready.json().catch(() => ({}));
          if (ready.ok && readyBody.status === "ready") {
            const ping = await pingUploadPath();
            if (ping === "ok" || ping === "unsupported") {
              els.serviceStatus.textContent = creditMode === "credits" && !wallet.hasCredit()
                ? "Orb service ready. Connect a wallet or buy testnet credits to use AI."
                : "Orb service ready.";
              els.serviceStatus.classList.add("ready");
              els.serviceStatus.classList.remove("failed");
              syncEnhanceStatus();
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
    els.serviceStatus.classList.add("failed");
    syncEnhanceStatus();
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
  if (!file || actionBusy) return;
  if (selectedFile) clearFile();
  const image = /\.(png|jpe?g|webp)$/i.test(file.name);
  const video = /\.(mp4|m4v|mov|webm)$/i.test(file.name);
  if (!image && !video) {
    showError(els.uploadError, "Unsupported file type. Choose a JPEG, PNG, WebP, MP4, MOV, M4V, or WebM file.");
    return;
  }
  if (file.size === 0) {
    showError(els.uploadError, "That file is empty. Choose a different file.");
    return;
  }
  if (file.size > (image ? MAX_IMAGE_BYTES : MAX_UPLOAD_BYTES)) {
    showError(els.uploadError, `That file exceeds the ${image ? 20 : 200} MB limit. Choose a smaller file.`);
    return;
  }
  selectedFile = file;
  els.uploadError.classList.add("hidden");
  els.uploadShell.classList.add("has-file");
  els.dropzone.classList.add("hidden");
  els.fileCard.classList.remove("hidden");
  els.fileName.textContent = file.name;
  els.fileMeta.textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB`;
  syncDecodeButton();
}

function clearFile() {
  selectedFile = null;
  visualAttemptKey = null;
  els.fileInput.value = "";
  els.uploadShell.classList.remove("has-file");
  els.fileCard.classList.add("hidden");
  els.dropzone.classList.remove("hidden");
  syncDecodeButton();
}

/* ---------- Visual AI flow ---------- */

function mapStage(stage) {
  if (!stage || stage === "Queued") return { step: "uploading", detail: "Waiting for the engine" };
  if (stage === "Inspecting video") return { step: "structure", detail: "Reading video metadata" };
  if (stage === "Analyzing image" || stage === "Analyzing visual reference" || stage === "Enhancing prompt") return { step: "structure", detail: stage };
  if (stage === "Composing prompt") return { step: "scenes", detail: stage };
  if (stage === "Detecting scene cuts") return { step: "scenes", detail: "Measuring scene changes" };
  if (stage === "Complete") return { step: "results", detail: "Preparing results" };
  return { step: "scenes", detail: stage };
}

function processingSteps() {
  const labels = STEP_LABELS[currentMode === "enhance" ? "enhance" : activeMediaKind === "image" ? "image" : "video"];
  return STEP_IDS.map((id, index) => ({ id, label: labels[index] }));
}

function renderSteps(activeStep, uploadDone) {
  const steps = processingSteps();
  const order = steps.map((s) => s.id);
  const activeIndex = order.indexOf(activeStep);
  els.stepList.innerHTML = "";
  steps.forEach((step, index) => {
    const li = document.createElement("li");
    let state = "pending";
    if (index < activeIndex || (uploadDone && activeStep === "results")) state = "done";
    if (step.id === activeStep) state = "active";
    li.className = `step-state-${state}`;
    li.innerHTML = `<span class="dot"></span>${step.label}`;
    els.stepList.appendChild(li);
  });
}

async function startVisual() {
  if (!selectedFile || actionBusy || !serviceReady || (creditMode === "credits" && !wallet.hasCredit())) return;
  activeMediaKind = /\.(png|jpe?g|webp)$/i.test(selectedFile.name) ? "image" : "video";
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
  els.phaseText.textContent = "Uploading reference";
  els.phaseDetail.textContent = "Sending the file to the Orb engine";

  const attemptId = visualAttemptKey || createUploadAttemptId();
  visualAttemptKey = attemptId;
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
      ? "This file couldn't be accessed through the selected source. Please select it again using Files or Browse instead of Gallery."
      : "The selected file could not be read from this device before upload.";
    fail(`${reason} (${precheckErrorName}) No upload was started and no retry was made. Reference: ${attemptId}.`);
    return;
  }

  const form = new FormData();
  form.append("file", selectedFile);
  let response;
  try {
    // The same-origin Vite proxy keeps the upload path and its canary intact.
    response = await fetchWithTimeout(
      uploadAttemptUrl(`/api/orb/${currentMode}/file`, attemptId),
      { method: "POST", body: form, headers: creditMode === "credits"
        ? { ...wallet.headers(), "X-Orb-Idempotency-Key": attemptId } : {} },
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
    fail(`Could not start ${currentMode}: ${data.detail || `upload failed (${response.status})`}`);
    return;
  }
  currentJobId = data.job_id;
  rememberPaidJob(currentJobId);
  selectedFile = null;
  clearFile();
  startPolling(currentJobId);
}

async function startEnhance() {
  const prompt = els.promptInput.value.trim();
  if (currentMode !== "enhance" || prompt.length < 3 || !serviceReady || actionBusy
      || (creditMode === "credits" && !wallet.hasCredit())) return;
  actionBusy = true;
  activeMediaKind = null;
  syncDecodeButton();
  if (!await isServiceReady()) {
    actionBusy = false;
    syncDecodeButton();
    return;
  }
  els.enhanceError.classList.add("hidden");
  showScreen("processing");
  els.jobError.classList.add("hidden");
  els.backBtn.classList.add("hidden");
  els.phaseText.textContent = "Enhancing prompt";
  els.phaseDetail.textContent = "Orb is refining your creative direction";
  els.uploadProgress.classList.add("is-indeterminate");
  renderSteps("structure", true);
  enhanceAttemptKey ||= createUploadAttemptId();
  try {
    const response = await fetchWithTimeout(apiUrl("/api/orb/enhance"), {
      method: "POST", headers: { "Content-Type": "application/json",
        ...(creditMode === "credits" ? { ...wallet.headers(), "X-Orb-Idempotency-Key": enhanceAttemptKey } : {}) },
      body: JSON.stringify({ prompt, output: els.enhanceOutput.value,
        style: els.enhanceStyle.value, detail: els.enhanceDetail.value }),
    }, UPLOAD_TIMEOUT_MS);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.job_id) throw new Error(data.detail || `request failed (${response.status})`);
    currentJobId = data.job_id;
    rememberPaidJob(currentJobId);
    startPolling(currentJobId);
  } catch (error) {
    actionBusy = false;
    showError(els.jobError, `Could not enhance prompt: ${error.message || "connection interrupted"}`);
    els.backBtn.classList.remove("hidden");
    syncDecodeButton();
  }
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
    const response = await fetchWithTimeout(apiUrl(`/api/jobs/${jobId}`),
      { headers: creditMode === "credits" ? wallet.headers() : {} });
    if (response.status === 404 || response.status === 410) {
      discardJob();
      return;
    }
    if (!response.ok) throw new Error(`Server returned ${response.status}.`);
    job = await response.json();
  } catch (error) {
    if (jobId !== currentJobId) return;
    pollFailures += 1;
    if (pollFailures < 3 && currentJobId === jobId) {
      schedulePoll(jobId, 1500 * pollFailures);
      return;
    }
    showError(els.jobError, `Connection interrupted: ${error.message || "could not check decoding status"}`);
    els.backBtn.classList.remove("hidden");
    actionBusy = false;
    if (creditMode === "credits") void wallet.refresh();
    syncDecodeButton();
    return;
  }
  if (jobId !== currentJobId) return;
  pollFailures = 0;
  const mapped = mapStage(job.stage || "");
  els.phaseText.textContent = processingSteps().find((s) => s.id === mapped.step).label;
  els.phaseDetail.textContent = job.stage || "";
  renderSteps(mapped.step, true);
  if (job.state === "complete") {
    clearTimeout(pollTimer);
    fetchResult(jobId);
  } else if (job.state === "error") {
    clearTimeout(pollTimer);
    forgetPaidJob();
    visualAttemptKey = null;
    enhanceAttemptKey = null;
    showError(els.jobError, `Analysis failed: ${job.error || "unknown error"}`);
    currentJobId = null;
    els.backBtn.classList.remove("hidden");
    actionBusy = false;
    syncDecodeButton();
  } else {
    schedulePoll(jobId);
  }
}

function discardJob() {
  clearTimeout(pollTimer);
  forgetPaidJob();
  currentJobId = null;
  actionBusy = false;
  clearFile();
  showScreen("home");
  showError(els.uploadError, "This analysis is no longer available on the server.");
}

async function fetchResult(jobId) {
  try {
    const response = await fetchWithTimeout(apiUrl(`/api/jobs/${jobId}/result`),
      { headers: creditMode === "credits" ? wallet.headers() : {} });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `status ${response.status}`);
    if (jobId !== currentJobId) return;
    renderResult(result);
    if (creditMode === "credits") void wallet.refresh();
  } catch (error) {
    if (jobId !== currentJobId) return;
    showError(els.jobError, `Could not load results: ${error.message}`);
    els.backBtn.classList.remove("hidden");
    actionBusy = false;
    syncDecodeButton();
  }
}

function fmtTime(seconds) {
  return `${Number(seconds).toFixed(1)}s`;
}

function renderResult(result) {
  forgetPaidJob();
  for (const url of privateMediaUrls) URL.revokeObjectURL(url);
  privateMediaUrls = [];
  actionBusy = false;
  syncDecodeButton();
  const video = result.video || {};
  const image = result.image || {};
  const media = result.image || result.video || {};
  const operation = result.operation || currentMode;
  els.resTitle.textContent = media.name || (operation === "enhance" ? "Enhanced prompt" : "Visual reference");
  els.resEyebrow.textContent = operation === "decode" ? "Decoded reference" : operation === "compose" ? "Composed from reference" : "Enhanced prompt";
  els.resMode.textContent = `AI ${operation} · ${result.provider || "configured provider"}`;
  els.resChips.innerHTML = "";
  const chips = [
    media.width && media.height ? `${media.width}×${media.height}` : null,
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

  els.resPreviewCard.classList.toggle("hidden", !media.preview_url);
  if (video.preview_url) {
    if (creditMode !== "credits") els.resVideo.src = apiUrl(video.preview_url);
    els.resVideo.classList.remove("hidden");
  }
  else { els.resVideo.removeAttribute("src"); els.resVideo.classList.add("hidden"); }
  if (image.preview_url) { if (creditMode !== "credits") els.resImage.src = apiUrl(image.preview_url); els.resImage.classList.remove("hidden"); }
  else { els.resImage.removeAttribute("src"); els.resImage.classList.add("hidden"); }

  els.resSummary.textContent = result.summary || "";
  els.resAnalysisCard.classList.toggle("hidden", !result.visual_analysis && !result.scenes?.length);
  els.resAnalysis.innerHTML = "";
  for (const [key, value] of Object.entries(result.visual_analysis || {})) {
    if (!value) continue;
    const group = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = key.replaceAll("_", " ");
    const detail = document.createElement("dd");
    detail.textContent = value;
    group.append(term, detail);
    els.resAnalysis.appendChild(group);
  }

  els.resScenes.innerHTML = "";
  for (const scene of result.scenes || []) {
    const card = document.createElement("div");
    card.className = "scene";
    const thumb = scene.frames && scene.frames.length ? apiUrl(scene.frames[0]) : "";
    if (thumb) {
      const img = document.createElement("img");
      img.loading = "lazy";
      if (creditMode === "credits") img.dataset.privateUrl = scene.frames[0];
      else img.src = thumb;
      img.alt = `Scene ${scene.index} thumbnail`;
      card.appendChild(img);
    }
    const info = document.createElement("div");
    info.className = "scene-meta";
    info.textContent = `Scene ${scene.index}: ${fmtTime(scene.start)} – ${fmtTime(scene.end)} · ${Number(scene.duration).toFixed(1)}s`;
    card.appendChild(info);
    els.resScenes.appendChild(card);
  }

  els.resPromptHeading.textContent = operation === "decode" ? "Reconstructed prompt" : operation === "compose" ? "New creative prompt" : "Enhanced prompt";
  els.resNotice.textContent = result.notice || "";
  els.resOriginal.classList.toggle("hidden", !result.original_prompt);
  els.resOriginalText.textContent = result.original_prompt || "";
  els.resPrompt.textContent = result.prompt || "";
  els.copyPrompt.disabled = !result.prompt;
  els.copyStatus.textContent = "";
  els.resRefinements.innerHTML = "";
  if (result.refinements?.length) {
    const title = document.createElement("strong");
    title.textContent = "Suggested refinements";
    const list = document.createElement("ul");
    for (const refinement of result.refinements) {
      const item = document.createElement("li");
      item.textContent = refinement;
      list.appendChild(item);
    }
    els.resRefinements.append(title, list);
    els.resRefinements.classList.remove("hidden");
  } else els.resRefinements.classList.add("hidden");

  showScreen("results");
  if (creditMode === "credits") void loadPrivateMedia(result);
}

async function loadPrivateMedia(result) {
  const load = async (path, node) => {
    try {
      const response = await fetchWithTimeout(apiUrl(path), { headers: wallet.headers() });
      if (!response.ok) return;
      const url = URL.createObjectURL(await response.blob());
      privateMediaUrls.push(url);
      node.src = url;
    } catch { /* The prompt remains usable if a preview cannot load. */ }
  };
  if (result.video?.preview_url) void load(result.video.preview_url, els.resVideo);
  if (result.image?.preview_url) void load(result.image.preview_url, els.resImage);
  for (const image of els.resScenes.querySelectorAll("img[data-private-url]")) void load(image.dataset.privateUrl, image);
}

/* ---------- Wiring ---------- */

els.chooseFileBtn.addEventListener("click", () => els.fileInput.click());
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
els.menuToggle.addEventListener("click", (event) => {
  event.stopPropagation();
  setMenuOpen(els.siteMenu.classList.contains("hidden"));
});
els.menuHome.addEventListener("click", (event) => {
  event.stopPropagation();
  if (actionBusy) return;
  clearTimeout(pollTimer);
  currentJobId = null;
  clearFile();
  showScreen("home");
});
els.menuAbout.addEventListener("click", (event) => {
  event.stopPropagation();
  setMenuOpen(false);
  setAboutOpen(true);
});
els.menuWallet.addEventListener("click", (event) => {
  event.stopPropagation();
  setMenuOpen(false);
  setAboutOpen(false);
  wallet.open();
});
for (const button of [els.uploadCreditsCta, els.enhanceCreditsCta]) button.addEventListener("click", () => wallet.open());
els.aboutClose.addEventListener("click", () => {
  setAboutOpen(false, true);
});
document.addEventListener("click", (event) => {
  if (!els.menuToggle.parentElement.contains(event.target)) setMenuOpen(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!document.getElementById("wallet-panel").classList.contains("hidden")) wallet.close(true);
    else if (!els.aboutPanel.classList.contains("hidden")) setAboutOpen(false, true);
    else if (!els.siteMenu.classList.contains("hidden")) {
      setMenuOpen(false);
      els.menuToggle.focus();
    }
  }
});
els.fileClear.addEventListener("click", clearFile);
els.decodeBtn.addEventListener("click", startVisual);
els.enhanceBtn.addEventListener("click", startEnhance);
els.promptInput.addEventListener("input", syncDecodeButton);
for (const input of [els.promptInput, els.enhanceOutput, els.enhanceStyle, els.enhanceDetail]) {
  input.addEventListener("input", () => { enhanceAttemptKey = null; });
  input.addEventListener("change", () => { enhanceAttemptKey = null; });
}
els.modeDecode.addEventListener("click", () => setMode("decode"));
els.modeCompose.addEventListener("click", () => setMode("compose"));
els.modeEnhance.addEventListener("click", () => setMode("enhance"));
els.copyPrompt.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(els.resPrompt.textContent);
    els.copyStatus.textContent = "Copied";
  } catch {
    els.copyStatus.textContent = "Copy unavailable. Select the prompt text to copy it.";
  }
});
els.backBtn.addEventListener("click", () => {
  currentJobId = null;
  actionBusy = false;
  syncDecodeButton();
  showScreen("home");
});
els.againBtn.addEventListener("click", () => {
  clearTimeout(pollTimer);
  currentJobId = null;
  actionBusy = false;
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
