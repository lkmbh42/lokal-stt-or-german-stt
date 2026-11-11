"""HTTP API routes.

All state lives on ``request.app.state`` (config, store, manager) — see
:func:`desktop_app.app.create_app`.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from engine import __version__ as engine_version
from engine.config import TranscribeOptions
from engine.formats import render
from engine.types import OutputFormat, TranscriptResult
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError

from desktop_app import __version__ as app_version
from desktop_app.config import ALLOWED_UPLOAD_EXTENSIONS, AppConfig
from desktop_app.db import JobRecord, JobStore
from desktop_app.jobs import JobManager, load_result

router = APIRouter(prefix="/api")

MEDIA_TYPES = {
    OutputFormat.TXT: "text/plain; charset=utf-8",
    OutputFormat.SRT: "application/x-subrip",
    OutputFormat.VTT: "text/vtt",
    OutputFormat.JSON: "application/json",
    OutputFormat.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}


class JobOut(BaseModel):
    id: str
    source: str
    filename: str
    status: str
    progress: float
    error: str | None
    created_at: str
    finished_at: str | None
    duration: float | None
    text_preview: str | None = None

    @classmethod
    def from_record(cls, record: JobRecord) -> JobOut:
        return cls(
            id=record.id,
            source=record.source,
            filename=record.original_filename,
            status=record.status,
            progress=record.progress,
            error=record.error,
            created_at=record.created_at,
            finished_at=record.finished_at,
            duration=record.duration,
        )


def _config(request: Request) -> AppConfig:
    return request.app.state.config  # type: ignore[no-any-return]


def _store(request: Request) -> JobStore:
    return request.app.state.store  # type: ignore[no-any-return]


def _manager(request: Request) -> JobManager:
    return request.app.state.manager  # type: ignore[no-any-return]


def _load_or_http(request: Request, record: JobRecord) -> TranscriptResult:
    """Load a transcript, mapping a missing/corrupt file to a clean HTTP error
    (404/422) instead of an unhandled 500."""
    try:
        return load_result(record, _config(request))
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                "Das Transkript zu diesem Auftrag wurde nicht gefunden. "
                "Die Datei fehlt oder wurde verschoben."
            ),
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Das Transkript konnte nicht gelesen werden (beschädigte Datei).",
        ) from None


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    config = _config(request)
    return {
        "status": "ok",
        "app_version": app_version,
        "engine_version": engine_version,
        "model": config.engine.model,
        "device": config.engine.device,
        "formats": [f.value for f in OutputFormat],
        "default_formats": [f.value for f in config.default_formats],
        "max_upload_mb": config.max_upload_mb,
    }


def _sanitize_filename(name: str | None) -> str:
    if not name:
        return "unbenannt"
    # display-only value: strip any path components a client might send
    return Path(name.replace("\\", "/")).name[:200] or "unbenannt"


@router.post("/jobs", status_code=201)
async def create_job(
    request: Request,
    file: UploadFile,
    initial_prompt: Annotated[str | None, Form()] = None,
    hotwords: Annotated[str | None, Form()] = None,
) -> JobOut:
    config = _config(request)
    original = _sanitize_filename(file.filename)
    extension = Path(original).suffix.lower()
    if extension in {".ds2", ".dss"}:
        # Olympus DSS Pro uses a proprietary codec ffmpeg cannot decode —
        # point the user at the required conversion step.
        raise HTTPException(
            status_code=400,
            detail=(
                "Olympus-Diktatdateien (.ds2 / .dss) können nicht direkt "
                "verarbeitet werden. Bitte zuerst mit Olympus ODMS in WAV oder "
                "MP3 umwandeln und die umgewandelte Datei hochladen."
            ),
        )
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Dateityp {extension or '(keiner)'} wird nicht unterstützt. "
                f"Erlaubt: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
            ),
        )

    job_id = uuid.uuid4().hex
    target = config.uploads_dir / f"{job_id}{extension}"
    limit = config.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Datei größer als {config.max_upload_mb} MB",
                    )
                out.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    if written == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Leere Datei")

    try:
        options = TranscribeOptions(
            initial_prompt=initial_prompt or None, hotwords=hotwords or None
        )
    except ValidationError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc

    record = await _manager(request).submit(target, original, options)
    return JobOut.from_record(record)


@router.get("/jobs")
def list_jobs(request: Request) -> list[JobOut]:
    return [JobOut.from_record(r) for r in _store(request).list()]


def _get_record(request: Request, job_id: str) -> JobRecord:
    record = _store(request).get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    return record


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str) -> JobOut:
    record = _get_record(request, job_id)
    out = JobOut.from_record(record)
    if record.status == "done" and record.transcript_path:
        # Preview is best-effort: a missing/corrupt transcript must not break
        # viewing the job itself — just omit the preview.
        try:
            out.text_preview = load_result(record, _config(request)).text[:2000]
        except (FileNotFoundError, ValueError):
            out.text_preview = None
    return out


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(request: Request, job_id: str) -> Response:
    record = _get_record(request, job_id)
    if record.status in ("queued", "processing"):
        _manager(request).cancel(job_id)
        return Response(status_code=204)
    config = _config(request)
    for stored in (record.audio_path, record.transcript_path):
        resolved = config.to_abs(stored)
        if resolved:
            resolved.unlink(missing_ok=True)
    _store(request).delete(job_id)
    return Response(status_code=204)


@router.get("/jobs/{job_id}/transcript")
def get_transcript(request: Request, job_id: str) -> Response:
    record = _get_record(request, job_id)
    if record.status != "done" or not record.transcript_path:
        raise HTTPException(status_code=409, detail="Auftrag ist noch nicht fertig")
    result = _load_or_http(request, record)
    return Response(
        content=result.model_dump_json(), media_type="application/json"
    )


@router.get("/jobs/{job_id}/export")
def export_job(request: Request, job_id: str, format: str = "txt") -> Response:
    record = _get_record(request, job_id)
    if record.status != "done" or not record.transcript_path:
        raise HTTPException(status_code=409, detail="Auftrag ist noch nicht fertig")
    result = _load_or_http(request, record)
    stem = Path(record.original_filename).stem or "transkript"

    if format == "all":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for fmt in OutputFormat:
                archive.writestr(f"{stem}.{fmt.value}", render(result, fmt))
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}.zip"'
            },
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
        headers={
            "Content-Disposition": f'attachment; filename="{stem}.{fmt.value}"'
        },
    )
