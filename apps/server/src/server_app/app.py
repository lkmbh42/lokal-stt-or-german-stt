"""FastAPI application factory for the team server."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request, Response
from sqlalchemy import select

from server_app import __version__
from server_app.api.admin import router as admin_router
from server_app.api.auth import router as auth_router
from server_app.api.jobs import router as jobs_router
from server_app.api.vocabulary import router as vocabulary_router
from server_app.auth.backend import AuthBackend, LocalAuthBackend
from server_app.auth.passwords import hash_password
from server_app.auth.tokens import TokenService
from server_app.config import ServerSettings, get_settings
from server_app.db import make_session_factory
from server_app.models import User
from server_app.ratelimit import RateLimiter

logger = logging.getLogger(__name__)

DispatchFn = Callable[[str], None]


def _default_dispatch(job_id: str) -> None:
    from server_app.tasks import transcribe_job_task

    transcribe_job_task.delay(job_id)


def bootstrap_admin(settings: ServerSettings, session_factory) -> None:  # type: ignore[no-untyped-def]
    """Create the initial admin from env — only when no user exists yet."""
    if not settings.bootstrap_admin_username or not settings.bootstrap_admin_password:
        return
    session = session_factory()
    try:
        if session.execute(select(User).limit(1)).scalar_one_or_none() is None:
            session.add(
                User(
                    username=settings.bootstrap_admin_username,
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role="admin",
                )
            )
            session.commit()
            logger.info(
                "Bootstrap admin %r angelegt.", settings.bootstrap_admin_username
            )
    finally:
        session.close()


def create_app(
    settings: ServerSettings | None = None,
    dispatch: DispatchFn | None = None,
    auth_backend: AuthBackend | None = None,
) -> FastAPI:
    """``dispatch`` and ``auth_backend`` are injectable for tests and for the
    future LDAP swap; production defaults are Celery and local Argon2."""
    settings = settings or get_settings()
    session_factory = make_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bootstrap_admin(settings, session_factory)
        logger.info("Team server ready (model=%s)", settings.engine.model)
        yield

    app = FastAPI(title="Lokal-STT Team Server", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.dispatch = dispatch or _default_dispatch
    app.state.auth_backend = auth_backend or LocalAuthBackend()
    app.state.tokens = TokenService(
        settings.secret_key,
        access_ttl=timedelta(minutes=settings.access_token_minutes),
        refresh_ttl=timedelta(days=settings.refresh_token_days),
    )
    app.state.auth_limiter = RateLimiter(
        settings.auth_rate_limit_attempts, settings.auth_rate_limit_window_seconds
    )
    if len(settings.secret_key) < 32:
        logger.warning(
            "STT_SECRET_KEY is shorter than 32 characters — generate a proper "
            "key with `openssl rand -hex 32`."
        )

    @app.middleware("http")
    async def db_session_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.db = session_factory()
        try:
            response = await call_next(request)
            request.state.db.commit()
            return response
        except Exception:
            request.state.db.rollback()
            raise
        finally:
            request.state.db.close()

    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(vocabulary_router)
    app.include_router(admin_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "model": settings.engine.model}

    return app
