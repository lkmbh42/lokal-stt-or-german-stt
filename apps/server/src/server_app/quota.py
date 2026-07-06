"""Server-side quota enforcement (audio minutes per day / month).

Resolution order: per-user limit (users table) → server default
(``STT_DEFAULT_DAILY_MINUTES`` / ``STT_DEFAULT_MONTHLY_MINUTES``) → 0 =
unlimited. Usage counts queued + processing + done jobs (canceled/failed
don't burn quota) using real duration when known, else the upload probe.
Windows are UTC calendar day / calendar month.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server_app.config import ServerSettings
from server_app.models import Job, User

_COUNTED_STATUSES = ("queued", "processing", "done")


class QuotaExceeded(Exception):
    def __init__(self, window: str, used_minutes: float, limit_minutes: float):
        self.window = window
        self.used_minutes = used_minutes
        self.limit_minutes = limit_minutes
        super().__init__(
            f"Kontingent erschöpft: {used_minutes:.1f} von {limit_minutes:.0f} "
            f"Minuten ({window}) bereits verwendet"
        )


@dataclass(frozen=True)
class QuotaStatus:
    daily_limit_minutes: float | None  # None = unlimited
    monthly_limit_minutes: float | None
    used_today_minutes: float
    used_month_minutes: float


def _window_starts(now: datetime) -> tuple[datetime, datetime]:
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    return day, month


def _used_seconds(session: Session, user_id: str, since: datetime) -> float:
    total = session.execute(
        select(
            func.coalesce(
                func.sum(func.coalesce(Job.duration, Job.estimated_duration, 0.0)), 0.0
            )
        ).where(
            Job.user_id == user_id,
            Job.status.in_(_COUNTED_STATUSES),
            Job.created_at >= since,
        )
    ).scalar_one()
    return float(total)


def effective_limits(user: User, settings: ServerSettings) -> tuple[float | None, float | None]:
    daily = user.daily_minutes_limit if user.daily_minutes_limit is not None else (
        settings.default_daily_minutes or None
    )
    monthly = user.monthly_minutes_limit if user.monthly_minutes_limit is not None else (
        settings.default_monthly_minutes or None
    )
    # an explicit per-user 0 also means unlimited
    return (daily or None), (monthly or None)


def quota_status(session: Session, user: User, settings: ServerSettings) -> QuotaStatus:
    day_start, month_start = _window_starts(datetime.now(timezone.utc))
    daily, monthly = effective_limits(user, settings)
    return QuotaStatus(
        daily_limit_minutes=daily,
        monthly_limit_minutes=monthly,
        used_today_minutes=_used_seconds(session, user.id, day_start) / 60.0,
        used_month_minutes=_used_seconds(session, user.id, month_start) / 60.0,
    )


def check_quota(
    session: Session, user: User, settings: ServerSettings, new_seconds: float
) -> None:
    """Raise :class:`QuotaExceeded` if adding ``new_seconds`` would cross a cap."""
    status = quota_status(session, user, settings)
    new_minutes = new_seconds / 60.0
    if (
        status.daily_limit_minutes is not None
        and status.used_today_minutes + new_minutes > status.daily_limit_minutes
    ):
        raise QuotaExceeded("heute", status.used_today_minutes, status.daily_limit_minutes)
    if (
        status.monthly_limit_minutes is not None
        and status.used_month_minutes + new_minutes > status.monthly_limit_minutes
    ):
        raise QuotaExceeded(
            "diesen Monat", status.used_month_minutes, status.monthly_limit_minutes
        )
