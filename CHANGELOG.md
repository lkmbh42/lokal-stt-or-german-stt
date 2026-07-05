# Changelog

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
