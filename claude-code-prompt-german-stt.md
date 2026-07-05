# CLAUDE CODE PROJECT BRIEF — Local German Speech-to-Text Platform

## ROLE

Act as a senior software engineering team lead with a full-stack engineer, an ML/inference engineer, and a DevOps engineer under your direction. You are building this **completely from scratch**, production-grade, no placeholders, no "TODO: implement later." Every phase must ship working, tested code before the next phase starts.

Work in **phase-gated mode**. After each phase, stop, summarize what was built, list open risks, and wait for the explicit gate phrase `GO PHASE <n>` before continuing. Do not skip ahead. Do not silently expand scope.

---

## PROJECT

Build a **fully local, offline-capable, high-accuracy German speech-to-text system**. No cloud APIs, no telemetry, no external network calls at runtime. Must run in air-gapped environments (model weights pre-downloaded during build/setup, never fetched at inference time).

Two deliverables from one shared core engine:

1. **Variant A — Single-User Desktop/Local Tool**
2. **Variant B — Multi-User Team Server** (~10 concurrent users, shared GPU)

---

## HARD REQUIREMENTS (non-negotiable)

- 100% local inference. No OpenAI API, no Azure Speech, no Google STT. Runtime network egress must be blockable with zero functional loss.
- German language accuracy is the primary optimization target — not multilingual generality.
- Must support both **file upload transcription** (batch: mp3/wav/m4a/mp4/flac) and **live microphone streaming transcription**.
- Output formats: `.txt`, `.srt`, `.vtt`, `.json` (word-level timestamps), `.docx`.
- Must degrade gracefully: GPU (CUDA) preferred, automatic CPU fallback.
- Codebase must be typed, tested, documented, and containerizable.
- No user data leaves the host/network. All storage is local disk/DB.
- **Primary users include blind and low-vision people. Accessibility is a first-class functional requirement, not a post-launch pass — see dedicated section below. A screen-reader user must complete every core workflow (record, upload, monitor progress, read/export transcript) using keyboard + screen reader alone, with no sighted assistance required.**

---

## CORE ENGINE (shared by both variants)

**ASR stack:**
- `faster-whisper` (CTranslate2 backend) as the inference engine — not raw `openai-whisper` (too slow, no int8/float16 quantization).
- Base model: `large-v3` (or `large-v3-turbo` for latency-sensitive scenarios). Force `language="de"`, disable auto language detection to avoid misdetection overhead and drift.
- Evaluate and document a German fine-tuned checkpoint (e.g. a CTranslate2-converted German Whisper fine-tune) as a swappable model option — engine must support hot-swapping model paths via config, not hardcoded.
- Voice Activity Detection: `silero-vad` pre-segmentation before ASR to cut hallucinations on silence and improve throughput.
- Support `initial_prompt` / hotword injection for domain vocabulary (names, product terms, acronyms) — expose this as a per-job parameter.
- Post-processing pipeline for German-specific normalization: number formatting, ordinal handling, punctuation cleanup, optional custom regex-based redaction hook (for PII).
- Optional speaker diarization module (`pyannote.audio`, local weights) — build as a pluggable stage, disabled by default, toggle per job.

**Engine must expose a clean internal Python API** (`transcribe(audio, config) -> TranscriptResult`) that both variants consume identically. Do not fork engine logic between variants — one core library, two deployment shells.

---

## ACCESSIBILITY (applies to both variants, all frontends)

Target: **WCAG 2.1 AA minimum**, AAA where feasible for contrast/motion. Screen readers in scope: NVDA + JAWS (Windows), VoiceOver (macOS). Test against at least NVDA — it's free and the most common on Windows enterprise fleets.

**Structural:**
- Semantic HTML only — real `<button>`, `<nav>`, `<main>`, `<label for=...>`. No `<div onClick>` interactive elements.
- Full keyboard operability: every action reachable via Tab/Shift+Tab, activatable via Enter/Space. No keyboard traps. Logical focus order matching visual/DOM order.
- Visible focus indicator on every focusable element (do not strip default outline without a replacement that meets 3:1 contrast).
- Correct heading hierarchy (`h1`→`h2`→`h3`, no skipped levels) so screen-reader users can navigate by heading.
- Skip-to-main-content link on every page.

**Core workflow-specific (this is where a generic a11y checklist isn't enough):**
- **File upload must not depend on drag-and-drop.** Drag-and-drop, if present, is an enhancement layered on top of a real `<input type="file">` triggered by a labeled, focusable button. Blind users cannot drag-and-drop reliably.
- **Live transcription output uses ARIA live regions** (`aria-live="polite"`) so new text is announced automatically without the user needing to move focus. Do **not** fire an announcement per token/word — batch updates (e.g. per sentence boundary or ~2–3s debounce) or the screen reader will become unusable noise. Give the user a setting to mute live announcements and instead get a completion cue.
- **Recording state changes (start/stop/error/done) must be announced non-visually** — an `aria-live="assertive"` status region for critical state changes (e.g. "Recording started," "Transcription complete," "Error: microphone not found"), plus an optional short audio cue (earcon) for start/stop/complete/error so state is perceivable even if the user isn't in the DOM region at that moment.
- **Keyboard shortcuts for every core action** (start/stop recording, upload, cancel job, export, switch output format) — document them in an in-app, screen-reader-reachable shortcuts panel, not just a tooltip.
- **Progress/queue status** (Variant B especially — "3rd in queue, ~2 min") must be exposed as text in a live region, not just a visual progress bar with no text equivalent.
- **Exported documents must themselves be accessible**: `.docx` output uses real heading/paragraph styles (not visual-only bold/font-size tricks) so it's navigable in Word with a screen reader; `.txt`/`.srt`/`.vtt` need no extra work here since they're inherently linear text.
- Error messages are specific and programmatically associated with their field (`aria-describedby`), not color-only or icon-only.
- No essential information conveyed by color alone (e.g. job status must have a text/icon label, not just a colored dot).
- Respect `prefers-reduced-motion`; avoid auto-playing audio other than the explicit earcons above.

**Bonus — leverage the product's own capability:** since this is a speech tool, consider a **voice-command mode for UI control itself** (e.g. "start recording," "export as text," "read back last transcript") layered on the same local ASR engine, restricted to a small fixed command grammar for reliability. This is a genuine differentiator for blind users and should be scoped as an optional Phase 4 stretch goal, not blocking core delivery.

**Testing requirement (not optional, gates Phase 1 and Phase 2 sign-off):**
- Automated: `axe-core` (or `@axe-core/react`) integrated into CI, zero critical/serious violations allowed to merge.
- Manual: a documented NVDA (or VoiceOver) walkthrough script covering every core workflow, delivered as a checklist artifact with pass/fail per step — treat this as a required test suite, not a nice-to-have.

---

## VARIANT A — SINGLE-USER LOCAL TOOL

**Target user:** one person, one machine, no auth needed, no network exposure beyond `localhost`.

**Architecture:**
- Backend: FastAPI app bound to `127.0.0.1` only (never `0.0.0.0`). Single process, single worker.
- Frontend: React + Vite, built as static assets and served directly by FastAPI — no separate frontend server, no Node runtime required at run-time.
- Packaging: ship as a single-command launcher (`run.py` or a PyInstaller-built executable) that starts the backend and opens the default browser to `http://127.0.0.1:<port>`.
- Storage: SQLite for job history/metadata. Transcripts and audio cached in a local `data/` directory.
- Live mic mode: WebSocket endpoint streaming audio chunks from the browser (Web Audio API) to the backend, incremental partial transcripts pushed back over the same socket.
- Batch mode: drag-and-drop file upload, background job processed in-process (async task, single GPU/CPU slot — no queue needed at this scale).
- No authentication. No multi-tenancy. Config file (`config.yaml`) controls model path, device, VAD sensitivity, output defaults.
- Export: one-click download for each output format; batch export as `.zip` for multi-file jobs.

**Explicit non-goals for Variant A:** no user accounts, no concurrent-job queueing, no RBAC, no external DB.

---

## VARIANT B — MULTI-USER TEAM SERVER (~10 users)

**Target user:** small internal team sharing one server with likely one shared GPU.

**Architecture:**
- `docker-compose` stack, all services containerized, no internet access required after image build:
  - `nginx` — reverse proxy, TLS termination (internal CA/self-signed cert supported), serves built frontend static assets.
  - `api` — FastAPI, stateless, horizontally scalable (though at 10 users, 1–2 replicas is enough).
  - `worker` — Celery (or RQ) worker(s) that own the GPU-bound `faster-whisper` engine instance(s). Job queue = Redis. This decouples "user uploads/requests" from "GPU actually transcribes," so 10 people hammering the API doesn't starve or crash inference.
  - `postgres` — users, jobs, audit log, quotas.
  - `redis` — queue broker + job status cache.
- **Auth:** local user table, Argon2 password hashing, JWT access/refresh tokens. Design the auth module with a clean interface so it can later be swapped for LDAP/AD bind auth without touching the rest of the app (this environment likely has an internal AD/LDAP — build the abstraction now, implement local-only auth first).
- **RBAC:** two roles minimum — `admin` (manage users, view all jobs, set quotas) and `user` (own jobs only).
- **Per-user isolation:** storage paths and DB rows scoped by `user_id`; users cannot list or fetch each other's jobs via the API (test this explicitly — authorization bypass on job IDs is the most likely vuln here).
- **Concurrency control:** GPU is a scarce single resource — worker pool size must match available GPU memory (config-driven, e.g. `MAX_CONCURRENT_JOBS=1` or `2` depending on VRAM and model size). Queue depth and ETA shown to users in the UI so a queued job doesn't look "stuck."
- **Quotas:** per-user daily/monthly minute caps (configurable), enforced server-side, not just UI-hidden.
- **Frontend:** React multi-page — login, job submission (upload + live-record-and-upload), personal job history, admin dashboard (user management, queue status, storage usage, model config).
- **Audit log:** who transcribed what, when, for how long — append-only table, admin-viewable, exportable.
- **Model provisioning for air-gap:** models must be baked into the Docker image (or mounted from a pre-staged local volume) at build/deploy time — the container must never attempt to pull from HuggingFace Hub at runtime. Document the offline model export/conversion step explicitly as part of the build pipeline.

**Explicit non-goals for Variant B v1:** no multi-tenant org hierarchy, no billing, no autoscaling beyond documented GPU worker count — this is an internal team tool, not a SaaS product.

---

## DELIVERY PHASES (gate after each)

**Phase 0 — Environment & Engine Foundation**
- Repo scaffold (monorepo: `/engine`, `/apps/desktop`, `/apps/server`, `/infra`).
- Core `engine` package: faster-whisper + VAD integration, config-driven model loading, GPU/CPU auto-detect, unit tests against sample German audio (provide test fixtures or a script to generate synthetic ones).
- CLI smoke test: `python -m engine.transcribe sample.wav --lang de` produces correct output formats.

**Phase 1 — Variant A (Single-User)**
- FastAPI localhost backend + React frontend, file upload batch transcription, all export formats.
- Live mic WebSocket streaming with partial results, delivered via debounced ARIA live regions per the Accessibility section (not raw token-by-token DOM updates).
- Full keyboard operability + screen-reader walkthrough (NVDA minimum) for: upload, record, monitor progress, export. `axe-core` clean in CI.
- Packaging script/executable. Manual test checklist delivered, including the accessibility walkthrough script as a pass/fail artifact.

**Phase 2 — Variant B (Multi-User) Core**
- Docker Compose stack, Postgres schema + migrations, Redis/Celery queue, worker wrapping the same `engine` package.
- Local auth (JWT + Argon2), RBAC, per-user job isolation with authorization tests.

**Phase 3 — Variant B Hardening**
- Quotas, audit log, admin dashboard, queue/ETA UI (queue position exposed as text in a live region, not visual-only), nginx TLS config, offline model provisioning docs/scripts.
- Same accessibility bar as Phase 1 applied to the multi-user frontend (login, dashboard, admin panel) — `axe-core` clean, NVDA walkthrough for login → submit job → check queue → retrieve transcript.
- Load test at ~10 concurrent users against a single GPU worker; document actual throughput/latency numbers, not estimates.

**Phase 4 — Cross-Cutting Polish**
- German-specific post-processing tuning pass (numbers, punctuation, custom vocabulary injection tested against real samples).
- Security pass: dependency audit, input validation on all upload endpoints, secrets management (no hardcoded keys/certs), rate limiting on auth endpoints.
- Optional stretch: voice-command UI control mode (fixed command grammar, reuses the core ASR engine) as described in the Accessibility section.
- Final docs: deployment runbook for both variants, model swap/update procedure, backup/restore for Postgres + storage volume, and the accessibility test scripts as living regression checklists.

---

## OUTPUT EXPECTATIONS PER PHASE

- Complete, runnable code — no stub functions.
- Tests included for every new module (pytest for backend/engine, minimal component tests for frontend where state logic is non-trivial).
- A short `CHANGELOG` entry and updated `README` per phase.
- Call out any tradeoff or assumption you made explicitly rather than silently picking one.

Begin with **Phase 0** now. Confirm the repo structure and engine design before writing extensive code, then implement it.
