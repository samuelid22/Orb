from __future__ import annotations

import threading
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from prometheus.performance import JobTiming, bind, current, observe, timed


@dataclass
class Job:
    id: str
    video_name: str
    state: str = "processing"
    stage: str = "Queued"
    error: str | None = None
    run_dir: Path | None = None
    tier: str = "advanced"
    source_file: str = "source.mp4"
    timing: JobTiming | None = field(default=None, repr=False, compare=False)


class JobManager:
    def __init__(self, max_workers: int = 1):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_workers = max_workers
        self._queued_job_ids: deque[str] = deque()
        self._active_job_ids: set[str] = set()
        self._queued_work: dict[str, Callable[[], None]] = {}

    @timed("job_creation")
    def create(
        self, video_name: str, tier: str = "advanced", source_file: str = "source.mp4"
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            video_name=video_name,
            tier=tier,
            source_file=source_file,
            timing=current(),
        )
        if job.timing is not None:
            job.timing.job_id = job.id
        with self._lock:
            self._jobs[job.id] = job
        return job

    def submit(self, job_id: str, work: Callable[[], None]) -> None:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown job: {job_id}")
            if job_id in self._active_job_ids or job_id in self._queued_work:
                return
            with bind(self._jobs[job_id].timing):
                observe("enqueue")
            self._queued_job_ids.append(job_id)
            self._queued_work[job_id] = work
            self._start_available_workers()

    def _start_available_workers(self) -> None:
        while self._queued_job_ids and len(self._active_job_ids) < self._max_workers:
            job_id = self._queued_job_ids.popleft()
            work = self._queued_work.pop(job_id)
            job = self._jobs.get(job_id)
            if job is None:
                continue
            self._active_job_ids.add(job_id)
            job.stage = "Starting analysis"
            self._executor.submit(self._run, job_id, work)

    def _run(self, job_id: str, work: Callable[[], None]) -> None:
        job = self.get(job_id)
        with bind(job.timing if job else None):
            observe("worker_start")
            status = "complete"
            try:
                work()
            except Exception as exc:
                status = "error"
                self.update(job_id, state="error", error=str(exc) or exc.__class__.__name__)
            finally:
                observe("finish", status)
                with self._lock:
                    self._active_job_ids.discard(job_id)
                    self._start_available_workers()

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
            self._queued_work.pop(job_id, None)
            try:
                self._queued_job_ids.remove(job_id)
            except ValueError:
                pass

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for name, value in fields.items():
                setattr(job, name, value)

    def public_info(self, job: Job) -> dict:
        with self._lock:
            info = {
                "id": job.id,
                "video_name": job.video_name,
                "state": job.state,
                "stage": job.stage,
                "error": job.error,
                "tier": job.tier,
            }
            try:
                info["queue_position"] = self._queued_job_ids.index(job.id)
            except ValueError:
                pass
            return info
