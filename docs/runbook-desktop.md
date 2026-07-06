# Deployment Runbook — Variant A (Single-User Desktop)

## Install (once per machine)

Requirements: Python ≥ 3.10, Node ≥ 20 (build time only), ffmpeg on PATH.
Windows additionally: Microsoft VC++ Redistributable x64
(`winget install Microsoft.VCRedist.2015+.x64`).

```bash
git clone <repo> && cd <repo>
python -m venv .venv && .venv\Scripts\activate      # POSIX: source .venv/bin/activate
pip install -e ./engine -e ./apps/desktop/backend
cd apps/desktop/frontend && npm ci && npm run build && cd ../..
cp apps/desktop/config.example.yaml apps/desktop/config.yaml   # then edit
```

Air-gapped machines: stage weights on a connected machine
(`python engine/scripts/download_model.py large-v3 --dest models`), copy the
directory over, set `engine.model: <path>` and `engine.local_files_only: true`.

## Run / stop

```bash
cd apps/desktop
python run.py --config config.yaml     # opens the browser; Ctrl+C stops
```

Optional autostart: register `pythonw.exe run.py --config config.yaml
--no-browser` as a scheduled task / systemd user unit.

## Upgrade

```bash
git pull
pip install -e ./engine -e ./apps/desktop/backend
cd apps/desktop/frontend && npm ci && npm run build
```

Job history (`apps/desktop/data/jobs.sqlite3`) is kept; the schema is
created idempotently at startup.

## Backup

Copy `apps/desktop/data/` (SQLite DB + uploads + transcripts) and
`config.yaml`. Restore = put them back.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ctranslate2.dll` load error (Windows) | Install the VC++ Redistributable (see engine/README.md, Windows notes) |
| "PyAV decoding unavailable … falling back to ffmpeg" in logs | Expected on hosts with app-control policies; ensure ffmpeg is on PATH |
| Port in use | `python run.py --port 0` (free port) or change `port:` in config.yaml |
| First job very slow | Model loads lazily on the first job (large-v3 ≈ 10–30 s from disk) |
| Mic not working | Browser permission; the app needs an AudioWorklet-capable browser (all current ones) |
| Frontend shows raw JSON at `/` | Frontend not built — run `npm run build` in apps/desktop/frontend |

Accessibility regression checklists: [a11y-walkthrough-desktop.md](a11y-walkthrough-desktop.md)
and [manual-test-checklist-desktop.md](manual-test-checklist-desktop.md).
