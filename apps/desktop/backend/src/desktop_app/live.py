"""Live microphone transcription over WebSocket.

Protocol (client ⇄ server):

* client → text JSON ``{"type": "start", "options": {...}}`` — begin session
* client → binary frames: 16 kHz mono **int16** PCM chunks
* client → text JSON ``{"type": "stop", "save": bool}`` — end session
* server → ``{"type": "ready"}`` after start
* server → ``{"type": "partial", "text": str}`` — rolling unconfirmed text
* server → ``{"type": "final", "segment": {...}}`` — a committed segment
  (sentence-ish boundary — the client announces these to screen readers)
* server → ``{"type": "stopped", "job_id": str | null}`` — after stop; when
  ``save`` was requested the full recording is re-transcribed as a normal
  batch job (word timestamps + full quality) and its id is returned
* server → ``{"type": "error", "message": str}``

Incremental strategy: pending audio is re-transcribed every ``tick_seconds``;
segments followed by ≥ ``silence_commit_seconds`` of trailing audio are
committed and dropped from the window, so the window stays small and partial
text stabilizes into finals at natural pauses.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from engine.config import TranscribeOptions
from engine.types import Segment
from fastapi import WebSocket, WebSocketDisconnect

from desktop_app.config import AppConfig
from desktop_app.jobs import JobManager, TranscriberLike

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000


@dataclass
class LiveSession:
    config: AppConfig
    manager: JobManager
    transcriber: TranscriberLike
    """Model used for the incremental live ticks — may be a smaller, faster
    one than the manager's batch model (config.live_engine). The save path
    always re-transcribes with the accurate batch model via the manager."""

    options: TranscribeOptions = field(default_factory=TranscribeOptions)
    pending: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=np.float32)
    )
    full_audio: list[np.ndarray] = field(default_factory=list)
    committed_seconds: float = 0.0
    committed_segments: list[Segment] = field(default_factory=list)

    def add_chunk(self, raw: bytes) -> None:
        chunk = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        self.pending = np.concatenate([self.pending, chunk])
        self.full_audio.append(chunk)

    @property
    def pending_seconds(self) -> float:
        return len(self.pending) / SAMPLE_RATE

    @property
    def total_seconds(self) -> float:
        return self.committed_seconds + self.pending_seconds

    def tick(self) -> tuple[list[Segment], str]:
        """Transcribe the pending window (blocking — run in a thread).

        Returns (newly committed segments, current partial text).
        """
        if self.pending_seconds < 1.0:
            return [], ""
        live_options = self.options.model_copy(
            update={"word_timestamps": False, "beam_size": self.config.live.beam_size}
        )
        result = self.transcriber.transcribe(self.pending, live_options)
        if not result.segments:
            # nothing but silence/noise: keep a short tail, drop the rest
            self._drop_seconds(max(self.pending_seconds - 2.0, 0.0))
            return [], ""

        last_end = result.segments[-1].end
        trailing_silence = self.pending_seconds - last_end
        force = self.pending_seconds >= self.config.live.max_pending_seconds
        if trailing_silence >= self.config.live.silence_commit_seconds or force:
            committed = [self._offset(seg) for seg in result.segments]
            self.committed_segments.extend(committed)
            self._drop_seconds(last_end)
            return committed, ""
        return [], result.text

    def _offset(self, seg: Segment) -> Segment:
        return Segment(
            id=len(self.committed_segments),
            start=seg.start + self.committed_seconds,
            end=seg.end + self.committed_seconds,
            text=seg.text,
            words=seg.words,
        )

    def _drop_seconds(self, seconds: float) -> None:
        samples = int(seconds * SAMPLE_RATE)
        self.pending = self.pending[samples:]
        self.committed_seconds += seconds

    def finalize(self) -> list[Segment]:
        """Commit whatever is left in the window (on stop)."""
        if self.pending_seconds < 0.5:
            return []
        live_options = self.options.model_copy(
            update={"word_timestamps": False, "beam_size": self.config.live.beam_size}
        )
        result = self.transcriber.transcribe(self.pending, live_options)
        committed = [self._offset(seg) for seg in result.segments]
        self.committed_segments.extend(committed)
        self._drop_seconds(self.pending_seconds)
        return committed

    def write_wav(self, path: Path) -> float:
        """Persist the full session audio; returns duration in seconds."""
        audio = (
            np.concatenate(self.full_audio)
            if self.full_audio
            else np.zeros(0, dtype=np.float32)
        )
        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm.tobytes())
        return len(pcm) / SAMPLE_RATE


def _parse_start_options(payload: dict[str, Any]) -> TranscribeOptions:
    raw = payload.get("options") or {}
    allowed = {"initial_prompt", "hotwords", "language"}
    return TranscribeOptions.model_validate(
        {k: v for k, v in raw.items() if k in allowed}
    )


async def handle_live_socket(
    websocket: WebSocket,
    config: AppConfig,
    manager: JobManager,
    live_transcriber: TranscriberLike,
) -> None:
    await websocket.accept()
    session: LiveSession | None = None
    save_requested = False
    stopped = False

    async def process_tick() -> None:
        assert session is not None
        committed, partial = await asyncio.to_thread(session.tick)
        for seg in committed:
            await websocket.send_json(
                {"type": "final", "segment": seg.model_dump(exclude={"words"})}
            )
        await websocket.send_json({"type": "partial", "text": partial})

    ticker: asyncio.Task[None] | None = None
    try:
        while not stopped:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            if (raw_bytes := message.get("bytes")) is not None:
                if session is None:
                    await websocket.send_json(
                        {"type": "error", "message": "send start before audio"}
                    )
                    continue
                session.add_chunk(raw_bytes)
                if session.total_seconds > config.live.max_session_seconds:
                    await websocket.send_json(
                        {"type": "error", "message": "maximale Aufnahmedauer erreicht"}
                    )
                    stopped = True
                continue

            payload = _json_or_none(message.get("text"))
            if payload is None:
                continue
            if payload.get("type") == "start":
                if session is not None:
                    await websocket.send_json(
                        {"type": "error", "message": "session already started"}
                    )
                    continue
                try:
                    options = _parse_start_options(payload)
                except ValueError as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue
                session = LiveSession(
                    config=config,
                    manager=manager,
                    transcriber=live_transcriber,
                    options=options,
                )
                ticker = asyncio.create_task(
                    _tick_loop(websocket, session, config, process_tick)
                )
                await websocket.send_json({"type": "ready"})
            elif payload.get("type") == "stop":
                save_requested = bool(payload.get("save"))
                stopped = True

        if ticker is not None:
            ticker.cancel()
        if session is not None:
            committed = await asyncio.to_thread(session.finalize)
            for seg in committed:
                await websocket.send_json(
                    {"type": "final", "segment": seg.model_dump(exclude={"words"})}
                )
            job_id: str | None = None
            if save_requested and session.full_audio:
                job_id = await _save_as_job(session, config, manager)
            await websocket.send_json({"type": "stopped", "job_id": job_id})
    except WebSocketDisconnect:
        logger.info("live socket disconnected")
    finally:
        if ticker is not None:
            ticker.cancel()


async def _tick_loop(
    websocket: WebSocket,
    session: LiveSession,
    config: AppConfig,
    process_tick: Any,
) -> None:
    try:
        while True:
            await asyncio.sleep(config.live.tick_seconds)
            await process_tick()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("live tick failed")
        with contextlib.suppress(RuntimeError):
            await websocket.send_json(
                {"type": "error", "message": "Transkription fehlgeschlagen"}
            )


async def _save_as_job(
    session: LiveSession, config: AppConfig, manager: JobManager
) -> str:
    import uuid

    stem = uuid.uuid4().hex
    filename = f"aufnahme-{stem[:8]}.wav"
    audio_path = config.uploads_dir / f"{stem}.wav"
    await asyncio.to_thread(session.write_wav, audio_path)
    record = await manager.submit(
        audio_path, filename, session.options, source="live"
    )
    return record.id


def _json_or_none(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    import json

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
