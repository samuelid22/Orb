"""Content-free, monotonic, request-to-worker performance observations.

Only fixed labels and numeric measurements are accepted. No observer failure
may change a request, job, retry, or settlement outcome.
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import json
import logging
import math
import threading
import time
import uuid
from contextlib import contextmanager

_LOG = logging.getLogger("uvicorn.error.orb_perf")
_LOG.setLevel(logging.INFO)
_CURRENT = contextvars.ContextVar("orb_performance", default=None)
_PURPOSE = contextvars.ContextVar("orb_ai_purpose", default="global_analysis")
_ATTEMPT = contextvars.ContextVar("orb_ai_attempt", default=1)
OPERATIONS = {"decode_visual", "compose_visual", "decode_image", "decode_video", "compose_image", "compose_video", "enhance"}
STAGES = {"multipart_receive_parse", "request_parse", "upload_receive", "upload_save", "authorization", "file_validation",
          "file_hash", "job_creation", "credit_reservation", "ffprobe", "ffprobe_process", "scene_detection", "frame_extraction",
          "ffmpeg", "frame_serialization", "response_parsing", "response_validation", "ai_retry_wait", "result_assembly",
          "artifact_persistence", "result_persistence", "credit_settlement", "cleanup"}
METRICS = {"input_bytes", "received_bytes", "receive_chunks", "video_duration_s", "width", "height", "scene_count",
           "frames", "scene_frames", "global_frames", "ffmpeg_launches", "ffprobe_launches", "paid", "reused"}
PURPOSES = {"scene_analysis", "global_analysis", "image_analysis", "compose_synthesis", "enhance"}
NUMERIC_KEYS = METRICS | {s + "_ms" for s in STAGES} | {
    "queue_ms", "processing_ms", "total_ms", "request_ms", "worker_start_ms", "ai_calls", "ai_total_ms", "ai_longest_ms", "ai_retries"}
GAUGES = {"input_bytes", "video_duration_s", "width", "height", "scene_count", "paid", "reused"}


def _emit(event, data):
    try:
        _LOG.info("%s %s", event, json.dumps(data, separators=(",", ":"), sort_keys=True))
    except Exception:
        pass


class JobTiming:
    def __init__(self, operation, clock=time.perf_counter):
        self.operation = operation if operation in OPERATIONS else "enhance"
        self.clock = clock
        self.started = clock()
        self.request_id = uuid.uuid4().hex
        self.job_id = None
        self.values = {}
        self.lock = threading.Lock()
        self.enqueued = None
        self.worker_started = None
        self.finished = False
        self.ai_sequence = 0
        self.ai_successes = 0
        self.ai_success_ms = 0.0

    def add(self, key, value):
        try:
            if key not in NUMERIC_KEYS:
                return
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                return
            with self.lock:
                self.values[key] = value if key in GAUGES else self.values.get(key, 0) + value
        except Exception:
            pass

    def metadata(self):
        return {"request_id": self.request_id, "job_id": self.job_id, "operation": self.operation}

    def set_operation(self, operation):
        if operation in OPERATIONS:
            self.operation = operation

    def request_parsed(self):
        self.add("multipart_receive_parse_ms" if self.operation.endswith("visual") else "request_parse_ms",
                 (self.clock() - self.started) * 1000)

    def enqueue(self):
        self.enqueued = self.clock()

    def worker_start(self):
        self.worker_started = self.clock()
        self.add("worker_start_ms", (self.worker_started - self.started) * 1000)
        if self.enqueued is not None:
            self.add("queue_ms", (self.worker_started - self.enqueued) * 1000)
        _emit("orb_perf", {**self.metadata(), "stage": "processing_start", "queue_ms": round(self.values.get("queue_ms", 0), 3)})

    def finish(self, status):
        try:
            status = status if status in {"complete", "error", "request_error", "reused"} else "error"
            with self.lock:
                if self.finished:
                    return
                self.finished = True
            end = self.clock()
            self.add("total_ms", (end - self.started) * 1000)
            if self.worker_started is not None:
                self.add("processing_ms", (end - self.worker_started) * 1000)
            with self.lock:
                values = {k: round(v, 3) for k, v in self.values.items()}
                for key in ("ai_calls", "ai_total_ms", "ai_longest_ms", "ai_retries", "file_hash_ms"):
                    values.setdefault(key, 0)
                if self.operation.endswith("video"):
                    for key in ("ffmpeg_launches", "ffprobe_launches", "frames", "scene_frames", "global_frames"):
                        values.setdefault(key, 0)
                values["ai_success_average_ms"] = round(self.ai_success_ms / self.ai_successes, 3) if self.ai_successes else 0
            _emit("orb_perf_summary", {**self.metadata(), "status": status, **values})
        except Exception:
            pass


def current():
    return _CURRENT.get()


def observe(method, *args):
    try:
        trace = current()
        if trace is not None:
            getattr(trace, method)(*args)
    except Exception:
        pass


def metric(name, value=1):
    observe("add", name, value)


@contextmanager
def bind(trace):
    token = _CURRENT.set(trace)
    try:
        yield
    finally:
        _CURRENT.reset(token)


@contextmanager
def stage(name):
    trace = current()
    start = time.perf_counter() if trace is not None else None
    try:
        yield
    finally:
        if start is not None:
            metric(name + "_ms", (time.perf_counter() - start) * 1000)


def timed(name):
    def decorate(function):
        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def wrapped(*args, **kwargs):
                with stage(name):
                    return await function(*args, **kwargs)
        else:
            @functools.wraps(function)
            def wrapped(*args, **kwargs):
                with stage(name):
                    return function(*args, **kwargs)
        return wrapped
    return decorate


@contextmanager
def purpose(name):
    token = _PURPOSE.set(name if name in PURPOSES else "global_analysis")
    try:
        yield
    finally:
        _PURPOSE.reset(token)


def categorized(name):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            with purpose(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate


@contextmanager
def attempt(number):
    token = _ATTEMPT.set(number)
    try:
        yield
    finally:
        _ATTEMPT.reset(token)


@contextmanager
def ai_call():
    trace = current()
    start = time.perf_counter()
    success = False
    try:
        yield
        success = True
    finally:
        if trace is not None:
            try:
                duration = (time.perf_counter() - start) * 1000
                with trace.lock:
                    trace.ai_sequence += 1
                    sequence = trace.ai_sequence
                    trace.values["ai_longest_ms"] = max(trace.values.get("ai_longest_ms", 0), duration)
                    if success:
                        trace.ai_successes += 1
                        trace.ai_success_ms += duration
                trace.add("ai_calls", 1)
                trace.add("ai_total_ms", duration)
                _emit("orb_perf", {**trace.metadata(), "stage": "ai_request", "purpose": _PURPOSE.get(),
                                   "sequence": sequence, "attempt": _ATTEMPT.get(),
                                   "duration_ms": round(duration, 3), "success": success})
            except Exception:
                pass


def retry_wait(seconds):
    metric("ai_retries")
    trace = current()
    if trace is not None:
        _emit("orb_perf", {**trace.metadata(), "stage": "ai_retry_wait", "purpose": _PURPOSE.get(),
                           "attempt": _ATTEMPT.get(), "planned_delay_ms": seconds * 1000})


def process_run(runner, tool, *args, **kwargs):
    metric(tool + "_launches")
    with stage("ffprobe_process" if tool == "ffprobe" else "ffmpeg"):
        return runner(*args, **kwargs)


class TimingMiddleware:
    """Observe ASGI receive without consuming, buffering, or altering the body."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        operation = {"/api/orb/decode/file": "decode_visual", "/api/orb/compose/file": "compose_visual",
                     "/api/orb/enhance": "enhance"}.get(path)
        if scope["type"] != "http" or scope.get("method") != "POST" or operation is None:
            return await self.app(scope, receive, send)
        trace = JobTiming(operation)
        status = 500

        async def observed_receive():
            with stage("upload_receive"):
                message = await receive()
            if message.get("type") == "http.request":
                metric("received_bytes", len(message.get("body", b"")))
                metric("receive_chunks")
            return message

        async def observed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        with bind(trace):
            try:
                _emit("orb_perf", {**trace.metadata(), "stage": "request_received"})
                await self.app(scope, observed_receive, observed_send)
            finally:
                trace.add("request_ms", (trace.clock() - trace.started) * 1000)
                with trace.lock:
                    values = {k: round(v, 3) for k, v in trace.values.items() if k in {
                        "request_ms", "multipart_receive_parse_ms", "request_parse_ms", "upload_receive_ms", "received_bytes", "receive_chunks"}}
                _emit("orb_perf_request", {**trace.metadata(), "http_status": status, **values})
                if status >= 400 or trace.job_id is None or trace.values.get("reused"):
                    trace.finish("reused" if trace.values.get("reused") else "request_error")
