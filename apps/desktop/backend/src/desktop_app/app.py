"""FastAPI application factory and entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from desktop_app.api import router
from desktop_app.config import AppConfig
from desktop_app.db import JobStore
from desktop_app.jobs import JobManager, TranscriberLike
from desktop_app.live import handle_live_socket

logger = logging.getLogger(__name__)


def _default_frontend_dist() -> Path:
    # backend/src/desktop_app/app.py -> apps/desktop/frontend/dist
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


def create_app(
    config: AppConfig | None = None,
    transcriber: TranscriberLike | None = None,
) -> FastAPI:
    """Build the app. ``transcriber`` is injectable for tests; by default the
    real engine is constructed (and loads weights lazily on the first job)."""
    config = config or AppConfig()
    config.ensure_dirs()

    engine: TranscriberLike
    if transcriber is None:
        from engine.transcriber import Transcriber

        engine = Transcriber(config.engine)
    else:
        engine = transcriber

    store = JobStore(config.db_path)
    manager = JobManager(config, store, engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await manager.start()
        logger.info(
            "Desktop STT ready on http://%s:%s (model=%s)",
            config.host,
            config.port,
            config.engine.model,
        )
        try:
            yield
        finally:
            await manager.stop()

    app = FastAPI(title="Lokal-STT Desktop", lifespan=lifespan)
    app.state.config = config
    app.state.store = store
    app.state.manager = manager
    app.include_router(router)

    @app.websocket("/ws/live")
    async def live_socket(websocket: WebSocket) -> None:
        await handle_live_socket(websocket, config, manager)

    dist = config.frontend_dist or _default_frontend_dist()
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        logger.warning(
            "Frontend build not found at %s — API only. "
            "Run `npm run build` in apps/desktop/frontend.",
            dist,
        )

    return app
