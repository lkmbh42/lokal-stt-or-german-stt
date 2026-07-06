# Changelog

## Phase 2 — Variant B Core: Multi-User Team Server (2026-07-06)

### Added
- `apps/server` (`server_app` package): FastAPI API around the shared engine
  with Postgres (SQLAlchemy 2.0 + Alembic migration incl. CI drift check),
  Celery/Redis queue, per-user scoped job endpoints, global queue-position
  reporting, upload validation, all export formats + zip.
- Auth: Argon2id password hashing, JWT access/refresh tokens with rotation
  and strict type separation, live `is_active` enforcement (deactivation
  locks out existing tokens), bootstrap admin from env. Auth logic sits
  behind a documented `AuthBackend` protocol so LDAP/AD bind auth can be
  swapped in without touching tokens, RBAC or job code.
- RBAC: `admin` (user management, all-jobs overview with owners, self-
  demotion guard) vs `user` (own jobs only).
- Per-user isolation: DB rows and storage paths scoped by `user_id`; foreign
  job ids answer 404 byte-identical to missing ids (no existence oracle) —
  covered by a dedicated authorization test suite.
- Celery worker wrapping the engine: one lazily-loaded engine per worker
  process, `STT_MAX_CONCURRENT_JOBS` = concurrency = GPU slots, Postgres-backed
  progress via `on_segment`, cooperative cancellation via DB flag,
  `acks_late` + no prefetch (GPU jobs are expensive).
- `infra/`: docker-compose stack (nginx, api, worker, postgres, redis),
  shared api/worker image, read-only pre-staged model volume
  (`local_files_only=true` — no runtime downloads), `.env.example`,
  configurable published port.
- CI: server job with real Postgres service (`alembic upgrade head` +
  `alembic check`), compose-config validation job.
- Tests: 35 server tests — auth flows, token abuse (cross-type, forged,
  expired), RBAC, isolation invariants, worker lifecycle/cancel/error paths.

### Verified end-to-end (full Docker stack, real model, air-gap config)
- `docker compose up` on this machine: admin bootstrap → user creation →
  login → upload through nginx → Redis/Celery → worker transcribed real
  German audio with weights mounted read-only (`local_files_only=true`) →
  verbatim result exported.
- Live isolation probes against the running stack: foreign job → 404,
  non-admin on admin routes → 403, admin overview shows owners.

### Explicit tradeoffs
- No refresh-token denylist yet (rotation + live deactivation mitigate;
  Phase 4 security pass). Auth rate limiting also Phase 4 per brief.
- TLS termination and the multi-user frontend land in Phase 3.

## Phase 1 — Variant A: Single-User Desktop Tool (2026-07-06)

### Added
- `apps/desktop/backend` (`desktop_app` package): FastAPI shell around the
  shared engine — loopback-only binding enforced by config validation,
  SQLite job store, single-slot async job runner with text progress and
  cooperative cancellation, upload validation (extension whitelist, size
  cap, filename sanitization), export endpoints for txt/srt/vtt/json/docx
  plus all-formats `.zip`.
- Live microphone transcription over WebSocket: rolling-window incremental
  ASR with silence-based segment commits (partials stabilize into finals at
  natural pauses); optional full-quality re-transcription of the recording
  as a saved history job.
- `apps/desktop/frontend`: accessible-first React + Vite UI in German —
  real labeled file input (drag-and-drop only as enhancement), debounced
  ARIA live regions with a `TranscriptBatcher` (sentence-batched, never
  token-by-token), assertive announcements + optional earcons for recording
  state changes, keyboard shortcuts with an in-app dialog, text-based
  progress, skip link, focus management; served statically by the backend.
- Engine: `on_segment` callback on `Transcriber.transcribe` (progress
  reporting + cooperative cancel).
- `run.py` single-command launcher (auto-opens browser, `--port 0` free-port
  mode). PyInstaller packaging evaluated and deferred — tradeoff documented
  in apps/desktop/README.md.
- Tests: 38 backend (stubbed engine), 26 frontend incl. an `axe-core`
  zero-violation gate on all views; GitHub Actions CI for engine, backend,
  frontend.
- Docs: NVDA walkthrough checklist (`docs/a11y-walkthrough-desktop.md`,
  gates sign-off) and manual test checklist
  (`docs/manual-test-checklist-desktop.md`).

### Verified end-to-end (real model, `base`, CPU)
- Upload → transcribe → export round-trip via HTTP: German verbatim output,
  all five formats + zip.
- Live WebSocket streaming at real-time pacing: incremental finals at
  sentence boundaries with correct rolling-window timestamp offsets.

## Phase 0 — Environment & Engine Foundation (2026-07-05)

### Added
- Monorepo scaffold: `/engine`, `/apps/desktop`, `/apps/server`, `/infra`.
- Core `engine` Python package (typed, `py.typed`, src layout):
  - `engine.config` — pydantic-validated `EngineConfig` / `TranscribeOptions`,
    YAML loading, config-driven model path (hot-swappable, name or local dir).
  - `engine.device` — GPU/CPU auto-detection via CTranslate2 with automatic
    CPU fallback and compute-type resolution (CUDA→float16, CPU→int8).
  - `engine.transcriber` — `Transcriber` wrapping faster-whisper with
    integrated Silero VAD pre-segmentation, forced `language="de"` default
    (auto-detect disabled), word-level timestamps, `initial_prompt`/hotword
    injection per job, lazy model loading and `swap_model()`.
  - `engine.pipeline` — pluggable post-ASR stage protocol (diarization will
    plug in here in a later phase).
  - `engine.postprocess` — German text normalization (spacing/punctuation,
    ordinals, optional decimal-comma and thousands grouping) and a
    regex-based PII redaction hook applied to segment *and* word text.
  - `engine.formats` — exporters for `.txt`, `.srt`, `.vtt`, `.json`
    (word-level timestamps), `.docx` (real Word heading/paragraph styles,
    document language set to de-DE for screen-reader correctness).
  - `engine.transcribe` — CLI: `python -m engine.transcribe sample.wav --lang de`.
  - `engine.audio` — local audio decoding with a PyAV → ffmpeg-CLI fallback
    (some locked-down Windows hosts block PyAV's native DLLs via
    application-control policy; both paths are fully offline).
- Test fixtures: `engine/scripts/make_fixtures.py` synthesizes real German
  speech via Windows SAPI (de-DE voice) plus silence/tone WAVs; fixtures are
  generated locally, no downloads.
- Offline model staging: `engine/scripts/download_model.py` snapshots
  CTranslate2-converted Whisper weights to a local directory for air-gapped
  deployment; engine supports `local_files_only` hard-offline mode.
- pytest suite: unit tests (no weights required) + `model`-marked integration
  tests against real German audio.
