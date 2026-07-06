# Variant A — Single-User Desktop Tool

Local German speech-to-text for one person on one machine. FastAPI backend
bound to `127.0.0.1` (validated, not just defaulted), React frontend served
as static assets by the same process — no Node runtime, no auth, no network
exposure.

## Start

```bash
# one-time setup (from repo root)
python -m venv .venv && .venv\Scripts\activate
pip install -e ./engine -e ./apps/desktop/backend
cd apps/desktop/frontend && npm install && npm run build && cd ../..

# run
cd apps/desktop
python run.py                  # starts server, opens the browser
python run.py --config config.yaml
```

Copy [config.example.yaml](config.example.yaml) to `config.yaml` to change
model, device, VAD sensitivity, data directory or live-mode tuning. For
air-gapped machines set `engine.local_files_only: true` and point
`engine.model` at a pre-staged directory (see `engine/scripts/download_model.py`).

## What it does

- **Batch:** upload mp3/wav/m4a/mp4/flac (multiple files), background
  transcription on a single CPU/GPU slot, progress as text, export as
  `.txt`, `.srt`, `.vtt`, `.json` (word timestamps), `.docx` or all-in-one `.zip`.
- **Live microphone:** WebSocket streaming with rolling partial text;
  segments are committed at natural pauses. Optionally the recording is
  re-transcribed in full quality afterwards and lands in the history.
- **German vocabulary injection:** per-job `initial_prompt` and hotwords.
- **History:** SQLite-backed job list with cancel/delete; files live under
  `data/`.

## Accessibility (core design constraint, not a feature)

- Full keyboard operability; skip-link; logical heading structure; visible
  focus indicators; German UI with `lang="de"`.
- Upload is a real labeled `<input type="file">` — drag-and-drop is an
  optional enhancement on top.
- Live transcript announcements are **batched per committed sentence**
  (never token-by-token), muteable in-app; recording state changes
  (start/stop/complete/error) go through an assertive live region plus
  optional earcons.
- Progress and queue status are exposed as text, not only visually.
- Shortcuts (documented in-app via the „Tastenkürzel" dialog):
  `Ctrl+Alt+1/2/3` sections, `Ctrl+Alt+R` record toggle, `Ctrl+Alt+K` help.
- Gates: `axe-core` runs in the frontend test suite (zero violations
  allowed); the manual NVDA walkthrough lives at
  [docs/a11y-walkthrough-desktop.md](../../docs/a11y-walkthrough-desktop.md).

## Architecture

```
backend/src/desktop_app/
  config.py   AppConfig (loopback-enforced) + engine/live sub-configs
  db.py       SQLite JobStore (short-lived connections, WAL)
  jobs.py     single-slot async worker; progress via engine on_segment;
              cooperative cancel
  live.py     WebSocket live session: rolling window, silence-based commits
  api.py      REST: /api/jobs (upload/list/get/delete), /export, /health
  app.py      app factory; serves frontend/dist statically
frontend/src/
  announcer.tsx      polite+assertive live regions, TranscriptBatcher
  audio/recorder.ts  AudioWorklet mic capture -> 16 kHz int16 PCM
  audio/earcons.ts   start/stop/complete/error cues
  views/             UploadView, RecordView, JobsView, ShortcutsDialog
run.py        single-command launcher (free-port mode: --port 0)
```

## Tests

```bash
pytest apps/desktop/backend/tests      # 38 tests, stubbed engine, no weights
cd apps/desktop/frontend && npm test   # 26 tests incl. axe-core a11y gate
```

## Packaging note (called-out tradeoff)

`run.py` + a virtualenv is the supported launcher. A PyInstaller onefile
build was evaluated and deliberately deferred: ctranslate2/onnxruntime ship
large native DLLs that PyInstaller must unpack per start, application-control
policies (see engine README, Windows notes) flag repacked DLLs, and model
weights should live outside the executable anyway. Revisit in Phase 4 if a
no-Python install is required.
