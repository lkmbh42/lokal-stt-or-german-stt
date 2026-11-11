"""Regression tests for the portability + robustness fixes.

Covers:
  * #1 stored paths are relative and survive the data dir moving (self-heal)
  * #2 a missing/deleted transcript yields a clean 404, not an unhandled 500
  * #3 jobs left 'processing' by a crash are failed on next startup (reaper)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from desktop_app.app import create_app
from desktop_app.config import AppConfig
from desktop_app.db import JobRecord, JobStore

from tests_helpers import upload

try:  # conftest helper (wait_for_status) is importable either way
    from conftest import wait_for_status
except ImportError:  # pragma: no cover
    from tests.conftest import wait_for_status  # type: ignore


# ---------------------------------------------------------------- #1 paths

def test_to_rel_to_abs_roundtrip(tmp_path: Path) -> None:
    cfg = AppConfig(data_dir=tmp_path / "data")
    p = cfg.uploads_dir / "abc.wav"
    rel = cfg.to_rel(p)
    assert rel == "uploads/abc.wav"  # stored relative, forward slashes
    assert not Path(rel).is_absolute()
    assert cfg.to_abs(rel) == cfg.uploads_dir / "abc.wav"
    assert cfg.to_abs(None) is None


def test_to_abs_reroots_a_moved_absolute_path(tmp_path: Path) -> None:
    """An absolute path from an OLD machine/location re-roots onto the current
    data dir — this is exactly the 500 we hit after the data folder moved PCs."""
    cfg = AppConfig(data_dir=tmp_path / "data")
    stale = r"C:\Users\someoneelse\OldPlace\data\transcripts\job123.json"
    resolved = cfg.to_abs(stale)
    assert resolved == cfg.transcripts_dir / "job123.json"


def test_stored_paths_are_relative(client: TestClient) -> None:
    resp = upload(client, "meeting.wav")
    job_id = resp.json()["id"]
    wait_for_status(client, job_id, "done")
    record = client.app.state.store.get(job_id)  # type: ignore[attr-defined]
    assert not Path(record.audio_path).is_absolute()
    assert not Path(record.transcript_path).is_absolute()
    assert record.audio_path.startswith("uploads/")
    assert record.transcript_path.startswith("transcripts/")


def test_transcript_survives_data_dir_move(
    tmp_path: Path, stub_transcriber: object
) -> None:
    """Create a job, then physically move the data dir and point a fresh app at
    the new location — the transcript still loads (truly portable)."""
    old = AppConfig(data_dir=tmp_path / "old", frontend_dist=tmp_path / "none")
    app1 = create_app(old, transcriber=stub_transcriber)  # type: ignore[arg-type]
    with TestClient(app1) as c1:
        job_id = upload(c1, "diktat.wav").json()["id"]
        wait_for_status(c1, job_id, "done")

    # relocate the whole data folder to a new path (as a USB stick / a different
    # user profile / another drive letter would). copytree, not rename: the
    # source's SQLite side-files stay open on Windows, and a real move/copy to a
    # new machine is what we're simulating anyway.
    moved = tmp_path / "moved"
    shutil.copytree(tmp_path / "old", moved)

    new = AppConfig(data_dir=moved, frontend_dist=tmp_path / "none")
    app2 = create_app(new, transcriber=stub_transcriber)  # type: ignore[arg-type]
    with TestClient(app2) as c2:
        got = c2.get(f"/api/jobs/{job_id}/transcript")
        assert got.status_code == 200
        assert "Müller" in got.text or got.json()["segments"]


# ------------------------------------------------------------ #2 clean errors

def test_missing_transcript_returns_404_not_500(client: TestClient) -> None:
    job_id = upload(client, "gone.wav").json()["id"]
    wait_for_status(client, job_id, "done")
    config: AppConfig = client.app.state.config  # type: ignore[attr-defined]
    record = client.app.state.store.get(job_id)  # type: ignore[attr-defined]

    # simulate the file disappearing (moved/renamed/cleaned up)
    config.to_abs(record.transcript_path).unlink()

    resp = client.get(f"/api/jobs/{job_id}/transcript")
    assert resp.status_code == 404
    assert "nicht gefunden" in resp.json()["detail"]

    # the job itself is still viewable (preview just omitted), not a 500
    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["text_preview"] is None


def test_export_missing_transcript_returns_404(client: TestClient) -> None:
    job_id = upload(client, "gone2.wav").json()["id"]
    wait_for_status(client, job_id, "done")
    config: AppConfig = client.app.state.config  # type: ignore[attr-defined]
    record = client.app.state.store.get(job_id)  # type: ignore[attr-defined]
    config.to_abs(record.transcript_path).unlink()

    resp = client.get(f"/api/jobs/{job_id}/export?format=txt")
    assert resp.status_code == 404


# -------------------------------------------------------------- #3 reaper

def test_fail_interrupted_marks_stuck_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.add(JobRecord(original_filename="a.wav", status="processing"))
    store.add(JobRecord(original_filename="b.wav", status="queued"))
    store.add(JobRecord(original_filename="c.wav", status="done"))

    reaped = store.fail_interrupted()
    assert reaped == 2
    statuses = {r.original_filename: r.status for r in store.list()}
    assert statuses == {"a.wav": "error", "b.wav": "error", "c.wav": "done"}
    stuck = next(r for r in store.list() if r.original_filename == "a.wav")
    assert stuck.error and "Neustart" in stuck.error


def test_startup_reaps_interrupted_job(
    tmp_path: Path, stub_transcriber: object
) -> None:
    """A job left 'processing' (app killed mid-run) is failed when the app
    next starts, instead of hanging forever."""
    cfg = AppConfig(data_dir=tmp_path / "data", frontend_dist=tmp_path / "none")
    cfg.ensure_dirs()
    store = JobStore(cfg.db_path)
    store.add(JobRecord(original_filename="stuck.wav", status="processing"))

    app = create_app(cfg, transcriber=stub_transcriber)  # type: ignore[arg-type]
    with TestClient(app):  # entering the context runs the lifespan startup
        pass

    job = next(r for r in store.list() if r.original_filename == "stuck.wav")
    assert job.status == "error"
