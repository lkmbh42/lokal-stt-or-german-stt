# Changelog

## 2026-07-09 — German model evaluation (Tier 1)

- New reproducible WER benchmark harness (`engine/scripts/benchmark.py`): 10
  natural German sentences synthesized locally, optional noise degradation,
  normalized WER, side-by-side model comparison.
- Evaluated `primeline/whisper-large-v3-turbo-german` (converted to CT2)
  against the deployed `large-v3-turbo`. **Conclusion: keep turbo.** Clean
  German 0.0 % vs 1.0 % (fine-tune adds a ß→ss spelling change); hard 0 dB
  noise 5.3 % vs 4.5 % (fine-tune marginally better, within sample noise).
  Not a decisive win; the custom dictionary is the better targeted lever.
  Full write-up + honest caveats in `docs/model-benchmark.md`.
- `torch`/`transformers` were used only for the one-time conversion — not
  runtime dependencies; Docker images are unaffected.

## 2026-07-09 — Custom vocabulary / correction dictionary (Variant B)

- Per-user **Wörterbuch**: each entry is a correct *term* (boosted into
  hotwords so the model recognizes it) plus optional *variants* (common
  mishears auto-corrected to the term). Applied automatically to every job —
  upload and recording alike.
- Engine: `CorrectionRule` + `TranscribeOptions.corrections` +
  `VocabularyCorrections` post-processing stage (whole-word, case-insensitive,
  sentence-initial capitalization preserved, applied to segment and word-level
  text). Runs after normalization, before redaction.
- Server: `VocabularyEntry` model + migration 0004, CRUD API
  `/api/vocabulary` (per-user, isolated), combined with any per-job hotwords.
- Frontend: Wörterbuch management view.
- Verified end-to-end on the live stack: a term/variant pair actually
  corrected the transcript coming out of the real worker. 11 engine + 12
  server + 3 frontend tests added.

## 2026-07-08 — Dictation mode: professional enhancement

- Much broader command vocabulary: square/curly brackets (`eckige/geschweifte
  Klammer auf/zu` → `[ ] { }`), `Schrägstrich` → `/`, `Prozentzeichen` → `%`,
  `Paragraf` → `§`, `Sternchen` → `*`, plus synonyms (`Klammer öffnen/
  schließen`, `Gänsefüßchen`, `Zeilenumbruch`) and `neuer Absatz` → blank line.
- Longest-match command resolution (3-word before 2-word before 1-word).
- Decimal comma: digits around a spoken "Komma" become "3,5" (attached).
- Capitalization directives: `großschreiben` / `kleinschreiben` before a word
  fix casing (handy for names Whisper lowercased).
- Verified against the full original stress sentence: reproduces
  `Ach, du meine Güte… (oder besser: Himmel!) – … : Kommas; Punkten; …`
  structure exactly. 27 engine tests for the stage.

## 2026-07-07 — Dictation mode (spoken punctuation)

- New opt-in **Diktatmodus**: spoken German command words are converted to
  the actual marks (`Komma`→`,`, `Klammer auf`→`(`, `Doppelpunkt`→`:`, …) —
  the only way to produce marks Whisper can't infer from audio. Implemented
  as an engine post-processing stage (`DictationCommands`) plus a
  `TranscribeOptions.dictation_mode` flag; Variant B exposes a toggle that
  applies to both recording and file upload.
- Robustness: only the exact singular command form triggers (so plural
  content words like "Kommas"/"Punkten" survive), Whisper's own duplicate
  punctuation is collapsed, spacing and capitalization are rebuilt, and
  ASR-split compounds ("Ausrufe Zeichen" → "Ausrufezeichen") are glued back
  before matching.
- Verified end-to-end on the live Variant B stack with the real
  large-v3-turbo model. 15 engine unit tests + 2 server API tests added.

## 2026-07-07 — Recording accuracy improvements

- **Variant A dual-model support**: new `live_engine` config option runs the
  live-recording preview on a small fast model while batch uploads and the
  full-quality re-transcription of saved recordings use the accurate main
  model. New `live.beam_size` knob for GPU hosts. Covered by a dedicated
  dual-model test.
- **Recommended model is now `large-v3-turbo`** for CPU machines (desktop
  default config and both deployment guides): verified on this corpus that
  it fixes recognition errors the `base` trial model made (e.g.
  "zweitausendsechsundzwanzig" → `2026`, where base produced `2006`) at
  roughly realtime speed on CPU. GPU servers keep `large-v3`.
- Deployment guides (DE + EN) gained an accuracy section: live preview is
  intentionally fast/rough, the saved transcript is authoritative; use the
  vocabulary field for names/terms.

## Phase 4 — Cross-Cutting Polish (2026-07-06)

### Security pass
- **Refresh-token registry** (migration `0003`): rotation revokes the used
  token, logout revokes explicitly, replayed tokens are rejected *and
  audited* (`auth.token_replayed`), deactivating a user revokes all their
  sessions. Closes the Phase 2 tradeoff.
- **Auth rate limiting**: per-IP sliding window on login/refresh
  (configurable, 429 + Retry-After); in-process by design at this scale,
  Redis path documented for wider scaling.
- **Dependency audits**: `pip-audit` clean; `npm audit` finding
  (esbuild dev-server advisory chain) resolved by upgrading both frontends
  to vite 8 / vitest 4 — all suites re-verified green, 0 vulnerabilities.
- nginx security headers (nosniff, frame-deny, referrer policy, CSP;
  HSTS in the TLS config); startup warning for weak `STT_SECRET_KEY`.

### German tuning pass (real samples, documented in docs/german-tuning-phase4.md)
- Seven-sentence corpus (currency, dates, decimals, big numbers,
  abbreviations, proper nouns) synthesized and run through the real engine:
  Whisper's native German number formatting confirmed correct — the
  conservative normalizer strategy is validated, opt-in rewrites stay off.
- Vocabulary injection A/B: hotwords fix proper nouns cleanly;
  `initial_prompt` with default conditioning caused prompt-echo duplication —
  **engine now disables `condition_on_previous_text` automatically when a
  prompt is set and the caller didn't choose explicitly** (regression-tested).

### Voice-command mode (stretch goal, Variant A)
- "Sprachsteuerung" toggle: fixed German command grammar (navigate sections,
  open help, read status, end voice mode) recognized through the same live
  WS + engine; closed grammar with umlaut-folding normalization
  (unit-tested); auto-pauses when an audio recording claims the microphone;
  commands documented in the in-app shortcuts dialog.

### Final documentation
- Deployment runbooks for both variants (`docs/runbook-desktop.md`,
  `docs/runbook-server.md` incl. security operations and restore drill),
  model swap/update procedure with validation checklist
  (`docs/model-management.md`). Accessibility walkthroughs remain the living
  regression checklists.

## Phase 3 — Variant B Hardening (2026-07-06)

### Added
- **Quotas**: per-user daily/monthly audio-minute caps (per-user override →
  server default → unlimited), enforced server-side at upload time via an
  ffprobe duration probe (rejects before the GPU works and rejects non-audio
  early); canceled/failed jobs don't burn quota; `GET /api/jobs/quota`.
- **Audit log**: append-only table (no mutation surface exists) covering
  logins (incl. failures with attempted username), job lifecycle
  (submit/complete/fail/cancel/delete with durations), quota rejections and
  user administration; admin list view with filters + CSV export
  (Excel-compatible BOM). Migration `0002`.
- **Queue ETA**: processing speed measured from recent jobs; queued jobs
  report `eta_seconds` alongside `queue_position` — the UI renders both as
  one German sentence in a live region ("Position 2 in der Warteschlange,
  voraussichtlich 3 Minuten"); ETA is null (omitted) until real speed data
  exists, never guessed.
- **Multi-user frontend** (`apps/server/frontend`): accessible German React
  UI — login (generic errors, `aria-describedby`), job submission (real file
  input + record-and-upload via AudioWorklet→WAV), history with text-based
  queue/progress status and announced transitions, quota banner, export
  downloads with auth headers; **admin dashboard** (user management incl.
  activate/deactivate and quota editing, audit log with filter + CSV,
  system status: queue depth, measured speed factor, model/device, per-user
  storage/minutes). axe-core gate on all views; token handling with
  transparent refresh.
- **nginx**: serves the built frontend, `/api` proxy; **TLS** variant config
  (`tls.conf.example`, TLS 1.2/1.3, HSTS) + self-signed/internal-CA cert
  script; published ports configurable.
- **Offline provisioning runbook** (`infra/PROVISIONING.md`): image
  save/load, model staging, egress verification checklist, model update and
  backup/restore procedures.
- **Load test**: `apps/server/scripts/load_test.py` + measured results in
  `docs/load-test-phase3.md` — 10 concurrent users, 20 jobs, 20/20 succeeded,
  queue throughput 2.95× realtime (base/CPU/Docker), job-list API p50 49 ms
  under load. GPU re-run flagged as pre-go-live task.
- NVDA walkthrough for the team UI (`docs/a11y-walkthrough-server.md`),
  CI job for the server frontend.
- Server suite now 50 backend tests + 11 frontend tests.

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
