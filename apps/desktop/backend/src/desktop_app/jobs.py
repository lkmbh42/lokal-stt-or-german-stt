"""Single-slot background job runner.

One asyncio worker consumes a queue and runs the blocking engine call in a
thread — exactly one transcription occupies the CPU/GPU at a time (the brief's
"single GPU/CPU slot — no queue system needed at this scale"). Progress is
derived from the engine's ``on_segment`` callback; cancellation is cooperative
(the callback raises between segments).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from engine.config import TranscribeOptions
from engine.types import Segment, TranscriptResult

from desktop_app.config import AppConfig
from desktop_app.db import JobRecord, JobStore, utcnow

logger = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class TranscriberLike(Protocol):
    """What the app needs from the engine — kept minimal so tests can stub it."""

    def transcribe(
        self,
        audio: Any,
        options: TranscribeOptions | None = None,
        on_segment: Callable[[Segment], None] | None = None,
    ) -> TranscriptResult: ...


class JobManager:
    def __init__(self, config: AppConfig, store: JobStore, transcriber: TranscriberLike):
        self._config = config
        self._store = store
        self._transcriber = transcriber
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._cancel_flags: dict[str, threading.Event] = {}
        self._worker_task: asyncio.Task[None] | None = None

    @property
    def transcriber(self) -> TranscriberLike:
        return self._transcriber

    async def start(self) -> None:
        self._worker_task = asyncio.create_task(self._worker(), name="job-worker")

    async def stop(self) -> None:
        if self._worker_task is not None:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

    async def submit(
        self,
        audio_path: Path,
        original_filename: str,
        options: TranscribeOptions,
        source: str = "upload",
    ) -> JobRecord:
        record = JobRecord(
            source=source,  # type: ignore[arg-type]
            original_filename=original_filename,
            audio_path=str(audio_path),
            options_json=options.model_dump_json(exclude_defaults=True),
        )
        self._store.add(record)
        self._cancel_flags[record.id] = threading.Event()
        await self._queue.put(record.id)
        logger.info("Job %s queued (%s)", record.id, original_filename)
        return record

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued or processing job. Returns False if not cancelable."""
        record = self._store.get(job_id)
        if record is None or record.status not in ("queued", "processing"):
            return False
        flag = self._cancel_flags.get(job_id)
        if flag is not None:
            flag.set()
        if record.status == "queued":
            self._store.update(job_id, status="canceled", finished_at=utcnow())
        return True

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            record = self._store.get(job_id)
            if record is None or record.status != "queued":
                continue  # deleted or canceled while waiting
            self._store.update(job_id, status="processing", started_at=utcnow())
            try:
                await asyncio.to_thread(self._run_job, record)
            except JobCancelled:
                self._store.update(
                    job_id, status="canceled", finished_at=utcnow()
                )
                logger.info("Job %s canceled", job_id)
            except Exception as exc:
                logger.exception("Job %s failed", job_id)
                self._store.update(
                    job_id, status="error", error=str(exc), finished_at=utcnow()
                )
            finally:
                self._cancel_flags.pop(job_id, None)

    def _run_job(self, record: JobRecord) -> None:
        options = TranscribeOptions.model_validate(json.loads(record.options_json))
        cancel_flag = self._cancel_flags.get(record.id) or threading.Event()
        duration_hint: float | None = None

        def on_segment(segment: Segment) -> None:
            nonlocal duration_hint
            if cancel_flag.is_set():
                raise JobCancelled()
            if duration_hint:
                progress = min(segment.end / duration_hint, 0.99)
                self._store.update(record.id, progress=progress)

        # a cheap duration probe would need a second decode; instead the first
        # engine callback carries no total — we set the hint from info after
        # the fact for *future* segments by pre-decoding here:
        from engine.audio import decode_audio

        waveform = decode_audio(record.audio_path or "")
        duration_hint = len(waveform) / 16_000.0

        result = self._transcriber.transcribe(waveform, options, on_segment=on_segment)
        if cancel_flag.is_set():
            raise JobCancelled()

        transcript_path = self._config.transcripts_dir / f"{record.id}.json"
        transcript_path.write_text(result.model_dump_json(), encoding="utf-8")
        self._store.update(
            record.id,
            status="done",
            progress=1.0,
            duration=result.info.duration,
            transcript_path=str(transcript_path),
            finished_at=utcnow(),
        )
        logger.info("Job %s done (%.1fs audio)", record.id, result.info.duration)


def load_result(record: JobRecord) -> TranscriptResult:
    if record.transcript_path is None:
        raise FileNotFoundError(f"job {record.id} has no transcript")
    raw = Path(record.transcript_path).read_text(encoding="utf-8")
    return TranscriptResult.model_validate_json(raw)
