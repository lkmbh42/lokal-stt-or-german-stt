# `engine` — Core German STT Package

The shared ASR core consumed by both product variants. One library, two
deployment shells — engine logic is never forked.

## Architecture

```
engine/
  config.py        EngineConfig (process-lifetime) / TranscribeOptions (per-job), YAML loading
  device.py        CUDA detection, auto CPU fallback, compute-type resolution
  transcriber.py   Transcriber: faster-whisper + integrated Silero VAD, lazy load, hot-swap
  pipeline.py      Post-ASR stage protocol (normalization, redaction; diarization plug point)
  postprocess/     German text normalization + regex PII redaction
  formats/         txt / srt / vtt / json (word timestamps) / docx (accessible styles)
  transcribe.py    CLI: python -m engine.transcribe
```

Public API (identical for both variants):

```python
from engine import EngineConfig, TranscribeOptions, Transcriber

engine = Transcriber(EngineConfig(model="large-v3"))          # lazy — loads on first job
result = engine.transcribe("meeting.mp3", TranscribeOptions(
    initial_prompt="Anthropic, Kubernetes, Frau Dr. Weber",   # domain vocabulary
    redaction_rules=[{"pattern": r"\b\d{2}\.\d{2}\.\d{4}\b"}] # PII hook
))
result.text                     # plain text
result.segments[0].words        # word-level timestamps
engine.swap_model("./models/whisper-german-ct2")              # hot-swap, no restart
```

Key decisions (called out per the brief):

- **VAD**: faster-whisper's integrated `vad_filter` **is** Silero VAD
  (onnxruntime backend). Using it instead of a separate `silero-vad` + torch
  dependency keeps the install lean and the pre-segmentation identical.
- **Language auto-detection is unreachable** — `TranscribeOptions.language`
  defaults to `de` and rejects empty values. This avoids detection latency
  and misdetection drift on short/noisy German audio.
- **Concurrency**: `Transcriber` serializes jobs with a lock. GPU scheduling
  (queueing, worker pools) belongs to the deployment shells, not the engine.
- **Normalization is conservative by default**: spacing/punctuation/ordinal
  fixes on; decimal-comma and thousands-grouping rewrites opt-in per job
  (aggressive numeric rewriting is a WER risk until tuned in Phase 4).
- **Redaction covers word-level output too** — `.json` exports word text, so
  redacting only segment text would leak PII.
- **Diarization** (pyannote.audio) is not in Phase 0; `pipeline.Stage` is its
  designed plug point (a diarizer fills `Segment.speaker`, and all exporters
  already render speaker labels — covered by tests).

## CLI

```bash
python -m engine.transcribe sample.wav --lang de                    # txt to ./out
python -m engine.transcribe meeting.mp3 --formats all --output-dir out
python -m engine.transcribe call.m4a --hotwords "Anthropic GmbH" \
    --initial-prompt "Protokoll der Vorstandssitzung"
python -m engine.transcribe x.wav --model ./models/faster-whisper-large-v3 --local-files-only
```

## Configuration

See [config.example.yaml](config.example.yaml) for the full annotated
reference. Precedence: CLI flags > `--config` YAML > built-in defaults.

## Model provisioning (air-gap)

Runtime downloads are disabled with `local_files_only: true` — the required
production setting. Stage weights on a connected machine:

```bash
python engine/scripts/download_model.py large-v3 --dest ./models
```

## German fine-tuned checkpoints (swappable option)

The engine takes any CTranslate2 model directory via `model:` — a German
fine-tune is a config change, not a code change. Evaluated candidates:

| Checkpoint | Notes |
|---|---|
| `openai/whisper large-v3` (default) | Strong German out of the box; best general robustness. |
| `primeline/whisper-large-v3-german` | German fine-tune; reported WER gains on German benchmarks (Common Voice de). Requires CT2 conversion (below). |
| `primeline/whisper-large-v3-turbo-german` | Turbo-based German fine-tune — the latency-sensitive option for live streaming in Phase 1. Requires CT2 conversion. |

Convert a transformers checkpoint to CTranslate2 once, on a connected machine:

```bash
pip install ctranslate2 transformers[torch]
ct2-transformers-converter --model primeline/whisper-large-v3-turbo-german \
    --output_dir models/whisper-large-v3-turbo-german-ct2 \
    --copy_files tokenizer.json preprocessor_config.json --quantization float16
```

Then `model: models/whisper-large-v3-turbo-german-ct2`. A/B evaluation of
these checkpoints against real domain audio is scheduled for the Phase 4
German tuning pass; until then `large-v3` is the default.

## Windows notes (dev machines)

- CTranslate2 needs the **Microsoft Visual C++ Redistributable (x64)**. If
  `import ctranslate2` fails with `Could not find module ... ctranslate2.dll`,
  install it: `winget install Microsoft.VCRedist.2015+.x64`.
- Hosts with an application-control policy (WDAC / Smart App Control) may
  block PyAV's native DLLs (`Eine Anwendungssteuerungsrichtlinie hat diese
  Datei blockiert`). The engine detects this and transparently falls back to
  decoding via the `ffmpeg` CLI — install ffmpeg and keep it on `PATH`.
  Containerized deployments (Linux) use PyAV normally.

## Tests

```bash
pytest engine/tests -m "not model"   # unit tests — no weights, fully offline
pytest engine/tests -m model         # integration — real model on real German audio
```

Fixtures are generated locally (`python engine/scripts/make_fixtures.py`,
Windows SAPI de-DE voice — no downloads). Integration tests use the `base`
model by default; override with `STT_TEST_MODEL=small` etc.
