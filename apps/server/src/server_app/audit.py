"""Append-only audit trail.

Who transcribed what, when, for how long — plus auth and admin events.
Write path is this one function; there is deliberately no update/delete
API or helper anywhere in the codebase.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from server_app.models import AuditLog, User

logger = logging.getLogger(__name__)

# canonical action names (searchable in the admin UI)
LOGIN = "auth.login"
LOGIN_FAILED = "auth.login_failed"
JOB_SUBMITTED = "job.submitted"
JOB_COMPLETED = "job.completed"
JOB_FAILED = "job.failed"
JOB_CANCELED = "job.canceled"
JOB_DELETED = "job.deleted"
QUOTA_REJECTED = "quota.rejected"
USER_CREATED = "user.created"
USER_UPDATED = "user.updated"


def record(
    session: Session,
    action: str,
    *,
    user: User | None = None,
    user_id: str | None = None,
    username: str | None = None,
    detail: str = "",
    ip: str | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user.id if user else user_id,
            username=username or (user.username if user else ""),
            action=action,
            detail=detail[:2000],
            ip=ip,
        )
    )
