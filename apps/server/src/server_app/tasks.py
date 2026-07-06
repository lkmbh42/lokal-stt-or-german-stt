"""Celery application and the transcription task.

The worker owns the GPU: it holds exactly one lazily-loaded engine instance
per worker process, and worker concurrency (``STT_MAX_CONCURRENT_JOBS``)
decides how many run in parallel — the API never touches model weights.

``run_transcription_job`` is a plain function so tests (and future
alternative dispatchers) can execute it without a broker.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

from celery import Celery

from server_app.config import ServerSettings, get_settings
from server_app.db import make_session_factory, session_scope
from server_app.models import Job, utcnow

if TYPE_CHECKING:
    from engine.transcriber import Transcriber

logger = logging.getLogger(__name__)

celery_app = Celery(
    "stt",
    broker=os.environ.get("STT_REDIS_URL", "redis://redis:6379/0"),
)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # a GPU job is expensive: never prefetch
    task_ignore_result=True,  # job state lives in Postgres, not in Redis
    broker_connection_retry_on_startup=True,
)

_transcriber: Transcriber | None = None


def get_transcriber(settings: ServerSettings) -> Transcriber:
    """One engine per worker process, loaded on first job."""
    global _transcriber
    if _transcriber is None:
        from engine.transcriber import Transcriber

        _transcriber = Transcriber(settings.engine)
    return _transcriber


class JobCancelled(Exception):
    pass


@celery_app.task(name="server_app.transcribe_job")  # type: ignore[untyped-decorator]
def transcribe_job_task(job_id: str) -> None:
    settings = get_settings()
    run_transcription_job(job_id, settings, get_transcriber(settings))


def run_transcription_job(job_id: str, settings: ServerSettings, transcriber: Any) -> None:
    """Execute one job end to end; safe to call from any process."""
    from engine.audio import decode_audio
    from engine.config import TranscribeOptions

    factory = make_session_factory(settings.database_url)

    with session_scope(factory) as session:
        job = session.get(Job, job_id)
        if job is None or job.status != "queued":
            logger.info("job %s skipped (missing or not queued)", job_id)
            return
        if job.cancel_requested:
            job.status = "canceled"
            job.finished_at = utcnow()
            return
        job.status = "processing"
        job.started_at = utcnow()
        user_id = job.user_id
        audio_path = job.audio_path
        options = TranscribeOptions.model_validate(json.loads(job.options_json))

    def check_cancel() -> bool:
        with session_scope(factory) as session:
            row = session.get(Job, job_id)
            return bool(row and row.cancel_requested)

    try:
        waveform = decode_audio(audio_path or "")
        duration = len(waveform) / 16_000.0

        def on_segment(segment: Any) -> None:
            if check_cancel():
                raise JobCancelled()
            if duration > 0:
                with session_scope(factory) as session:
                    row = session.get(Job, job_id)
                    if row is not None:
                        row.progress = min(segment.end / duration, 0.99)

        result = transcriber.transcribe(waveform, options, on_segment=on_segment)

        transcripts = settings.transcripts_dir(user_id)
        transcripts.mkdir(parents=True, exist_ok=True)
        transcript_path = transcripts / f"{job_id}.json"
        transcript_path.write_text(result.model_dump_json(), encoding="utf-8")

        with session_scope(factory) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = "done"
            job.progress = 1.0
            job.duration = result.info.duration
            job.transcript_path = str(transcript_path)
            job.finished_at = utcnow()
        logger.info("job %s done (%.1fs audio)", job_id, result.info.duration)
    except JobCancelled:
        with session_scope(factory) as session:
            job = session.get(Job, job_id)
            if job is not None:
                job.status = "canceled"
                job.finished_at = utcnow()
        logger.info("job %s canceled", job_id)
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        with session_scope(factory) as session:
            job = session.get(Job, job_id)
            if job is not None:
                job.status = "error"
                job.error = str(exc)
                job.finished_at = utcnow()
