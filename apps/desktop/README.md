# Variant A — Single-User Desktop/Local Tool

**Status: not started — gated behind Phase 0 sign-off (`GO PHASE 1`).**

Planned scope (from the project brief):

- FastAPI backend bound to `127.0.0.1` only, single process/worker.
- React + Vite frontend built to static assets and served by FastAPI —
  no Node runtime needed at run-time.
- Batch file upload transcription + live microphone streaming over WebSocket
  with debounced ARIA-live partial results.
- SQLite job history, local `data/` storage, `config.yaml` driven.
- Single-command launcher that starts the backend and opens the browser.
- Full keyboard operability and NVDA-tested screen-reader workflows;
  `axe-core` clean in CI (gates Phase 1 sign-off).

This app consumes the shared [`engine`](../../engine) package — no forked
inference logic.
