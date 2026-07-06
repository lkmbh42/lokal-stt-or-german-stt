# Model Management — Swap / Update Procedure

The engine takes any CTranslate2 model directory via config — swapping
models is an operational task, never a code change.

## 1. Stage the model (connected machine)

Official Whisper sizes:

```bash
python engine/scripts/download_model.py large-v3 --dest models
python engine/scripts/download_model.py large-v3-turbo --dest models   # latency-sensitive
```

German fine-tunes (or any HF transformers Whisper checkpoint) need one
conversion:

```bash
pip install ctranslate2 "transformers[torch]"
ct2-transformers-converter --model primeline/whisper-large-v3-turbo-german \
    --output_dir models/whisper-large-v3-turbo-german-ct2 \
    --copy_files tokenizer.json preprocessor_config.json --quantization float16
```

## 2. Point the deployment at it

| Variant | Setting |
|---|---|
| Desktop | `config.yaml` → `engine.model: <path>`, restart `run.py` |
| Server | `infra/.env` → `STT_ENGINE__MODEL=/models/<dir>`, `docker compose restart worker api` |

Keep `local_files_only: true` in production — a typo'd path fails loudly
instead of downloading. Keep the previous model directory until sign-off
(rollback = revert the setting + restart).

## 3. Validate before sign-off (30 minutes)

1. `pytest engine/tests -m model` with `STT_TEST_MODEL=<path>` — mechanics.
2. Run the **tuning corpus** from
   [german-tuning-phase4.md](german-tuning-phase4.md) and compare against the
   documented tables — numbers/dates/umlauts formatting and the
   hotwords A/B must not regress.
3. Transcribe 2–3 real domain recordings; spot-check names and terminology
   (add persistent problem terms to users' hotwords guidance).
4. Server: re-run the [load test](load-test-phase3.md) — bigger models change
   throughput and therefore quota/ETA expectations; adjust
   `STT_MAX_CONCURRENT_JOBS` to VRAM (large-v3 float16 ≈ 4.7 GB/slot).

## Compatibility notes

- The engine forces `language="de"`; multilingual checkpoints are fine,
  English-only (`*.en`) checkpoints are not.
- `compute_type: auto` resolves float16 on CUDA / int8 on CPU; quantization
  chosen at conversion time only bounds what's available, CTranslate2
  converts at load if needed.
- Whisper `tiny`–`large-v3(-turbo)` all work; VAD and word timestamps are
  model-independent (Silero + alignment run outside the checkpoint).
