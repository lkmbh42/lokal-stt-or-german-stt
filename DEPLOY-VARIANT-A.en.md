# Variant A — Desktop Tool: Deployment & Run, Step by Step

Single-user tool: one machine, one person, no login, binds to `127.0.0.1`
only. This guide goes from a blank machine to the running application.

---

## Part 1 — Install prerequisites (one-time)

You need:

| Software | Version | Check with |
|---|---|---|
| Python | ≥ 3.10 | `python --version` |
| Node.js | ≥ 20 (build-time only) | `node --version` |
| ffmpeg | any recent version, on PATH | `ffmpeg -version` |
| git | any | `git --version` |

**Windows additionally:** Microsoft Visual C++ Redistributable x64 (without
it, the inference library fails to load):

```powershell
winget install Microsoft.VCRedist.2015+.x64
```

ffmpeg on Windows, e.g.: `winget install Gyan.FFmpeg` (open a new terminal
afterward so PATH picks it up).

Linux (Debian/Ubuntu): `sudo apt install python3-venv nodejs npm ffmpeg git`

---

## Part 2 — Get and install the project (one-time)

Run all commands from the repository root. Windows examples use
PowerShell; Linux/macOS differences are noted inline.

**Step 1 — Get the code:**

```powershell
git clone <repo-url> lokal-stt
cd lokal-stt
```

**Step 2 — Create and activate a Python virtual environment:**

```powershell
python -m venv .venv
.\.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
```

(You'll see `(.venv)` in front of the prompt once activated.)

**Step 3 — Install backend packages** (engine + desktop app; takes a few
minutes, downloads faster-whisper among others):

```powershell
pip install -e ./engine -e ./apps/desktop/backend
```

**Step 4 — Build the frontend** (one-time; Node isn't needed at runtime
afterward):

```powershell
cd apps\desktop\frontend
npm ci
npm run build
cd ..\..\..
```

**Step 5 — Create the config file:**

```powershell
copy apps\desktop\config.example.yaml apps\desktop\config.yaml
```

Then open `apps\desktop\config.yaml` in an editor and pick a model:

```yaml
engine:
  model: large-v3     # best accuracy, ~3 GB download on first job
  # model: small      # good balance on CPU-only machines
  # model: base       # fastest, for quick trials
  device: auto        # uses a CUDA GPU if present, otherwise CPU
```

**Step 6 (air-gapped machines only):** pre-download the model on a
connected machine and copy it over:

```powershell
python engine\scripts\download_model.py large-v3 --dest models
```

Transfer the `models\faster-whisper-large-v3` folder to the target machine
and set in `config.yaml`:

```yaml
engine:
  model: ./models/faster-whisper-large-v3
  local_files_only: true    # blocks any download attempt
```

---

## Part 3 — Run and use it

**Start:**

```powershell
cd apps\desktop
..\..\.venv\Scripts\python.exe run.py --config config.yaml
```

Your default browser opens automatically at `http://127.0.0.1:8710`.
(If it doesn't, open that address manually.)

**Using the app:**

1. **Upload file** — select audio file(s) (mp3/wav/m4a/mp4/flac), optionally
   enter domain vocabulary, click "Transkription starten". Progress appears
   under "Verlauf & Export" (History & Export).
2. **Record** — "Aufnahme starten" (or `Ctrl+Alt+R`), allow microphone
   access, speak. Text appears live; after stopping, the recording is
   re-transcribed at full quality.
3. **History & Export** — download finished transcripts as
   txt/srt/vtt/json/docx, or all of them zipped.
4. `Ctrl+Alt+K` shows every keyboard shortcut and voice command;
   "Sprachsteuerung starten" enables voice-command control.

**Stop:** `Ctrl+C` in the terminal. All data (history, transcripts) lives
under `apps\desktop\data\` and persists across restarts.

**Useful start variants:**

```powershell
python run.py --config config.yaml --port 0          # pick a free port
python run.py --config config.yaml --no-browser      # don't open a browser
python run.py --config config.yaml -v                # verbose logging
```

---

## Part 4 — Updating

```powershell
git pull
.\.venv\Scripts\activate
pip install -e ./engine -e ./apps/desktop/backend
cd apps\desktop\frontend && npm ci && npm run build
```

History and configuration are preserved.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Could not find module ... ctranslate2.dll` (Windows) | Install the VC++ Redistributable (Part 1) |
| Log shows "PyAV decoding unavailable … falling back to ffmpeg" | Expected on locked-down Windows hosts — ensure ffmpeg is on PATH |
| Port already in use | Use `--port 0` or change `port:` in config.yaml |
| First job takes a long time | The model loads on the first job (and downloads once for large-v3, unless pre-staged) |
| Browser shows raw JSON at `/` | Frontend wasn't built — redo Part 2, Step 4 |
| Microphone doesn't work | Check browser permission; requires a current, AudioWorklet-capable browser |

Further reading: [docs/runbook-desktop.md](docs/runbook-desktop.md)
(operations), [docs/model-management.md](docs/model-management.md) (model
swaps), [apps/desktop/README.md](apps/desktop/README.md) (architecture).
