"""Queue ETA and system statistics for the admin dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server_app.config import ServerSettings
from server_app.models import Job, User


def processing_speed(session: Session, sample: int = 5) -> float | None:
    """Audio-seconds transcribed per wall-clock second, from recent jobs.

    ``None`` until at least one job with usable timestamps has finished.
    """
    rows = session.execute(
        select(Job.duration, Job.started_at, Job.finished_at)
        .where(Job.status == "done", Job.duration.is_not(None))
        .order_by(Job.finished_at.desc())
        .limit(sample)
    ).all()
    audio = 0.0
    wall = 0.0
    for duration, started, finished in rows:
        if duration and started and finished and finished > started:
            audio += duration
            wall += (finished - started).total_seconds()
    if wall <= 0:
        return None
    return audio / wall


def eta_seconds_for(session: Session, job: Job, speed: float | None) -> int | None:
    """Rough completion estimate for a queued job: everything queued ahead
    plus the job itself, at the observed processing speed."""
    if job.status != "queued" or speed is None or speed <= 0:
        return None
    ahead_seconds = session.execute(
        select(func.coalesce(func.sum(func.coalesce(Job.estimated_duration, 0.0)), 0.0)).where(
            Job.status == "queued", Job.created_at < job.created_at
        )
    ).scalar_one()
    processing_remaining = session.execute(
        select(
            func.coalesce(
                func.sum(func.coalesce(Job.estimated_duration, 0.0) * (1.0 - Job.progress)),
                0.0,
            )
        ).where(Job.status == "processing")
    ).scalar_one()
    own = job.estimated_duration or 0.0
    return int((float(ahead_seconds) + float(processing_remaining) + own) / speed)


@dataclass(frozen=True)
class UserUsage:
    username: str
    job_count: int
    minutes_total: float
    storage_bytes: int


def system_stats(session: Session, settings: ServerSettings) -> dict[str, object]:
    queue_depth = session.execute(
        select(func.count()).select_from(Job).where(Job.status == "queued")
    ).scalar_one()
    processing = session.execute(
        select(func.count()).select_from(Job).where(Job.status == "processing")
    ).scalar_one()
    speed = processing_speed(session)

    per_user: list[UserUsage] = []
    users = session.execute(select(User).order_by(User.username)).scalars().all()
    for user in users:
        job_count, seconds = session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(func.coalesce(Job.duration, Job.estimated_duration, 0.0)), 0.0
                ),
            ).where(Job.user_id == user.id)
        ).one()
        per_user.append(
            UserUsage(
                username=user.username,
                job_count=int(job_count),
                minutes_total=round(float(seconds) / 60.0, 1),
                storage_bytes=_dir_size(settings.user_dir(user.id)),
            )
        )

    return {
        "queue_depth": int(queue_depth),
        "processing": int(processing),
        "speed_factor": round(speed, 2) if speed else None,
        "model": settings.engine.model,
        "device": settings.engine.device,
        "max_concurrent_jobs": settings.max_concurrent_jobs,
        "users": [vars(u) for u in per_user],
    }


def _dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
