# Load Test — Variant B, ~10 Concurrent Users (Phase 3)

Measured numbers, not estimates (project brief requirement). Reproduce with:

```bash
python apps/server/scripts/load_test.py --base-url http://localhost:8080 \
    --admin-password <pw> --users 10 --jobs-per-user 2 \
    --audio engine/tests/fixtures/german_sample.wav
```

## Environment (2026-07-06)

| | |
|---|---|
| Host | Windows 11 dev machine, Docker Desktop (WSL2 backend), **CPU only — no GPU** |
| Stack | full docker-compose: nginx → api → redis/celery → worker → postgres |
| Model | `base`, int8, `local_files_only=true` (mounted volume) |
| Worker slots | `STT_MAX_CONCURRENT_JOBS=1` (single shared inference slot) |
| Load | 10 users in parallel, 2 uploads each = 20 jobs à 12.4 s German audio (247.6 s total) |

## Results (20/20 jobs succeeded, zero errors)

| Metric | Value |
|---|---|
| Wall time, first login → last job done | **83.9 s** |
| Queue throughput | **2.95× realtime** (worker-measured speed factor: 3.11×) |
| End-to-end per job (submit → done): min / median / max | **11.0 s / 42.0 s / 74.3 s** |
| Job-list API latency under load: p50 / p95 / max | **49 ms / 402 ms / 1 658 ms** |
| Upload endpoint (400 KB file + ffprobe + quota check): p50 / p95 | **3 323 ms / 3 361 ms** |
| Login (Argon2id verification): p50 / p95 | **2 599 ms / 2 638 ms** |

Audit trail after the run: 20 × `job.submitted`, 20 × `job.completed` —
consistent with the client-side view.

## Reading the numbers

- **The queue design works as intended**: 20 jobs through one inference slot
  completed strictly serially; e2e max (74 s) ≈ queue drain time, while the
  API stayed responsive throughout (p50 49 ms). Users see honest queue
  positions and ETAs instead of timeouts.
- **Login cost is Argon2id, by design.** ~2.5 s p50 under 10 simultaneous
  logins is the memory-hard hash doing its job on a CPU-contended host, not
  an I/O problem. With sessions lasting 15 min (access token TTL), users log
  in rarely; if it ever matters, tune Argon2 parameters — do not swap the
  algorithm.
- **Upload p50 ~3.3 s** includes multipart transfer, ffprobe, and quota
  accounting while the same CPUs run inference. Acceptable at this scale;
  ffprobe is the first thing to move async if uploads grow large.
- **Throughput scales with the model/hardware, not the stack**: ~3× realtime
  with `base` on CPU means ~20 audio-minutes per wall-clock hour ≈ enough
  for light team use only. Production sizing per brief (large-v3, one GPU):
  expect roughly 5–15× realtime depending on GPU — **to be re-measured on
  GPU hardware; the harness and method above are the regression baseline.**

## Open follow-ups

- Re-run on the production GPU host with `large-v3` and record the same
  table (owner: deployment, before go-live).
- If `MAX_CONCURRENT_JOBS > 1` is enabled on a large GPU, re-verify VRAM
  headroom and that throughput scales before raising the worker concurrency.
