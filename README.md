# Lokal-STT — Local German Speech-to-Text Platform

A fully local, offline-capable, high-accuracy German speech-to-text system.
No cloud APIs, no telemetry, no network calls at inference time. Designed for
air-gapped environments: model weights are staged during build/setup and never
fetched at runtime.

Two deliverables share one core engine:

| Variant | Description | Status |
|---|---|---|
| **Engine** (`/engine`) | Shared ASR core: faster-whisper + Silero VAD, German post-processing, all export formats, CLI | **Phase 0 — delivered** |
| **Variant A** (`/apps/desktop`) | Single-user localhost tool (FastAPI + React, live mic + batch, accessible-first UI) | **Phase 1 — delivered** |
| **Variant B** (`/apps/server`) | Multi-user team server (~10 users, Docker Compose, auth/RBAC/quotas) | Phase 2/3 — pending gate |
| **Infra** (`/infra`) | Docker, nginx, TLS, offline model provisioning | Phase 2/3 — pending gate |

Quick start for Variant A: see [apps/desktop/README.md](apps/desktop/README.md)
(`python run.py` after setup). Accessibility test artifacts live in
[docs/](docs/).

## Hard requirements (summary)

- 100% local inference — runtime network egress can be blocked with zero functional loss.
- German accuracy is the primary optimization target (`language="de"` is forced; auto-detection is disabled).
- Batch file transcription (mp3/wav/m4a/mp4/flac) **and** live microphone streaming.
- Output formats: `.txt`, `.srt`, `.vtt`, `.json` (word-level timestamps), `.docx`.
- GPU (CUDA) preferred with automatic CPU fallback.
- Accessibility is a first-class requirement (WCAG 2.1 AA minimum, NVDA-tested workflows) — applies to the app frontends built in Phases 1–3.

## Repository layout

```
engine/          Core Python package (installable, typed, tested)
  src/engine/    Package source — see engine/README.md for architecture
  tests/         pytest suite (unit + model-marked integration tests)
  scripts/       Fixture generation, offline model staging
apps/
  desktop/       Variant A — single-user local tool        (Phase 1)
  server/        Variant B — multi-user team server        (Phase 2)
infra/           Containerization, nginx, TLS, air-gap provisioning (Phase 2/3)
```

## Quickstart (engine, Phase 0)

Requires Python ≥ 3.10 and `ffmpeg` on PATH (used by test fixture tooling;
decoding at runtime is handled in-process by PyAV).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     POSIX: source .venv/bin/activate
pip install -e ./engine[dev]

# Generate audio test fixtures (uses Windows SAPI German voice when available)
python engine/scripts/make_fixtures.py

# Unit tests (no model weights needed)
pytest engine/tests -m "not model"

# Integration tests + CLI smoke test (downloads a small model once; see
# "Air-gapped installs" below for offline staging)
pytest engine/tests -m model
python -m engine.transcribe engine/tests/fixtures/german_sample.wav --lang de --model tiny --formats all
```

## Air-gapped installs

At runtime the engine never downloads anything. Stage weights on a connected
machine, then transfer:

```bash
python engine/scripts/download_model.py large-v3 --dest ./models
```

Point `config.yaml` at the staged directory and lock the engine down:

```yaml
model: ./models/faster-whisper-large-v3
local_files_only: true
```

With `local_files_only: true`, a missing model is a hard error instead of a
download attempt. See [engine/README.md](engine/README.md) for full config reference.

## Development

- Formatting/linting: `ruff check engine` — typing: `cd engine && mypy src` (strict)
- Tests: `pytest engine/tests` (marker `model` = requires model weights)
- Phase gating: work proceeds phase-by-phase; each phase ships runnable,
  tested code and a CHANGELOG entry before the next begins.
