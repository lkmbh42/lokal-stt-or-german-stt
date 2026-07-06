"""Per-user job endpoints.

Isolation invariant: every query in this module filters on
``Job.user_id == current_user.id``. Requests for another user's job id
return **404** (not 403) so job ids can't be probed for existence — this is
covered by explicit authorization tests.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from engine.config import TranscribeOptions
from engine.formats import render
from engine.types import OutputFormat, TranscriptResult
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server_app import audit
from server_app.auth.deps import CurrentUser, get_db
from server_app.config import ServerSettings
from server_app.models import Job
from server_app.probe import ProbeError, probe_duration_seconds
from server_app.quota import QuotaExceeded, check_quota, quota_status
from server_app.schemas import JobOut, QuotaOut
from server_app.stats import eta_seconds_for, processing_speed

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ALLOWED_UPLOAD_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".flac"}

MEDIA_TYPES = {
    OutputFormat.TXT: "text/plain; charset=utf-8",
    OutputFormat.SRT: "application/x-subrip",
    OutputFormat.VTT: "text/vtt",
    OutputFormat.JSON: "application/json",
    OutputFormat.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}


def get_server_settings(request: Request) -> ServerSettings:
    return request.app.state.settings  # type: ignore[no-any-return]


def dispatch_job(request: Request, job_id: str) -> None:
    request.app.state.dispatch(job_id)


def _sanitize_filename(name: str | None) -> str:
    if not name:
        return "unbenannt"
    return Path(name.replace("\\", "/")).name[:200] or "unbenannt"


def _own_job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user_id)
    ).scalar_one_or_none()
    if job is None:
        # 404 for both "doesn't exist" and "not yours": no id oracle
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    return job


def _queue_position(db: Session, job: Job) -> int | None:
    """1-based position across ALL users' queued jobs (one shared GPU)."""
    if job.status != "queued":
        return None
    ahead = db.execute(
        select(func.count())
        .select_from(Job)
        .where(Job.status == "queued", Job.created_at < job.created_at)
    ).scalar_one()
    return int(ahead) + 1


@router.post("", status_code=201)
async def create_job(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[ServerSettings, Depends(get_server_settings)],
    file: UploadFile,
    initial_prompt: Annotated[str | None, Form()] = None,
    hotwords: Annotated[str | None, Form()] = None,
) -> JobOut:
    original = _sanitize_filename(file.filename)
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Dateityp {extension or '(keiner)'} wird nicht unterstützt. "
                f"Erlaubt: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
            ),
        )

    try:
        options = TranscribeOptions(
            initial_prompt=initial_prompt or None, hotwords=hotwords or None
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc

    job_id = uuid.uuid4().hex
    uploads = settings.uploads_dir(user.id)
    uploads.mkdir(parents=True, exist_ok=True)
    target = uploads / f"{job_id}{extension}"
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Datei größer als {settings.max_upload_mb} MB",
                    )
                out.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    if written == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Leere Datei")

    try:
        estimated = probe_duration_seconds(target)
    except ProbeError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        check_quota(db, user, settings, estimated)
    except QuotaExceeded as exc:
        target.unlink(missing_ok=True)
        audit.record(
            db,
            audit.QUOTA_REJECTED,
            user=user,
            detail=f"{original} ({estimated / 60:.1f} min): {exc}",
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    job = Job(
        id=job_id,
        user_id=user.id,
        original_filename=original,
        audio_path=str(target),
        estimated_duration=estimated,
        options_json=options.model_dump_json(exclude_defaults=True),
    )
    db.add(job)
    audit.record(
        db,
        audit.JOB_SUBMITTED,
        user=user,
        detail=f"{original} ({estimated / 60:.1f} min), job {job_id}",
        ip=request.client.host if request.client else None,
    )
    db.flush()
    out_schema = JobOut.from_model(
        job,
        queue_position=_queue_position(db, job),
        eta_seconds=eta_seconds_for(db, job, processing_speed(db)),
    )
    db.commit()
    dispatch_job(request, job_id)
    return out_schema


@router.get("")
def list_jobs(
    user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> list[JobOut]:
    jobs = (
        db.execute(
            select(Job)
            .where(Job.user_id == user.id)
            .order_by(Job.created_at.desc(), Job.id.desc())
        )
        .scalars()
        .all()
    )
    speed = processing_speed(db)
    return [
        JobOut.from_model(
            j,
            queue_position=_queue_position(db, j),
            eta_seconds=eta_seconds_for(db, j, speed),
        )
        for j in jobs
    ]


@router.get("/quota", response_model=QuotaOut)
def my_quota(
    request: Request, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> QuotaOut:
    settings = get_server_settings(request)
    status = quota_status(db, user, settings)
    return QuotaOut(**vars(status))


@router.get("/{job_id}")
def get_job(
    job_id: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> JobOut:
    job = _own_job_or_404(db, user.id, job_id)
    out = JobOut.from_model(
        job,
        queue_position=_queue_position(db, job),
        eta_seconds=eta_seconds_for(db, job, processing_speed(db)),
    )
    if job.status == "done" and job.transcript_path:
        out.text_preview = _load_result(job).text[:2000]
    return out


@router.delete("/{job_id}", status_code=204)
def delete_job(
    request: Request,
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    job = _own_job_or_404(db, user.id, job_id)
    ip = request.client.host if request.client else None
    if job.status in Job.CANCELABLE:
        # cooperative cancel: the worker checks this flag between segments
        job.cancel_requested = True
        if job.status == "queued":
            job.status = "canceled"
        audit.record(
            db, audit.JOB_CANCELED, user=user, detail=f"job {job_id}", ip=ip
        )
        return Response(status_code=204)
    for path in (job.audio_path, job.transcript_path):
        if path:
            Path(path).unlink(missing_ok=True)
    db.delete(job)
    audit.record(
        db,
        audit.JOB_DELETED,
        user=user,
        detail=f"{job.original_filename}, job {job_id}",
        ip=ip,
    )
    return Response(status_code=204)


@router.get("/{job_id}/export")
def export_job(
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    format: str = "txt",
) -> Response:
    job = _own_job_or_404(db, user.id, job_id)
    if job.status != "done" or not job.transcript_path:
        raise HTTPException(status_code=409, detail="Auftrag ist noch nicht fertig")
    result = _load_result(job)
    stem = Path(job.original_filename).stem or "transkript"

    if format == "all":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for fmt in OutputFormat:
                archive.writestr(f"{stem}.{fmt.value}", render(result, fmt))
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{stem}.zip"'},
        )

    try:
        fmt = OutputFormat(format)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekanntes Format {format!r}. Erlaubt: "
            f"{', '.join(f.value for f in OutputFormat)} oder 'all'",
        ) from None
    return Response(
        content=render(result, fmt),
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{stem}.{fmt.value}"'},
    )


def _load_result(job: Job) -> TranscriptResult:
    raw = Path(job.transcript_path or "").read_text(encoding="utf-8")
    return TranscriptResult.model_validate_json(raw)
