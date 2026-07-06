# Infrastructure — Variant B stack

Docker Compose deployment for the [team server](../apps/server/README.md).

```
docker-compose.yml    nginx, api, worker, postgres, redis (+ named volumes)
Dockerfile.server     one image for api & worker (different commands)
nginx/default.conf    reverse proxy; TLS termination lands in Phase 3
.env.example          all knobs — copy to .env, set secrets
models/               pre-staged CTranslate2 weights (git-ignored, mounted ro)
```

## Bring-up

```bash
cp .env.example .env                 # set STT_SECRET_KEY, POSTGRES_PASSWORD, admin pw
python ../engine/scripts/download_model.py large-v3 --dest models
docker compose up --build -d
curl http://localhost:${STT_HTTP_PORT:-8080}/api/health
```

Migrations run automatically on API start (`alembic upgrade head`).

## Air-gapped deployment

1. On a connected machine: `docker compose build`, then
   `docker save lokal-stt-api | gzip > stt-image.tar.gz`; stage weights with
   `download_model.py`.
2. Transfer image + `models/` + this directory to the target host;
   `docker load < stt-image.tar.gz`.
3. `STT_ENGINE__LOCAL_FILES_ONLY=true` (default) guarantees no runtime
   download attempts — block egress at the firewall with zero functional loss.

## GPU

Install `nvidia-container-toolkit`, uncomment `gpus: all` on the `worker`
service, set `STT_ENGINE__DEVICE=cuda`. Size `STT_MAX_CONCURRENT_JOBS` to
VRAM: large-v3 float16 ≈ 4.7 GB per concurrent job.

## Phase 3 additions (planned)

TLS (internal CA / self-signed) in nginx, serving the built multi-user
frontend, backup/restore runbook for `pg-data` + `stt-data` volumes.
