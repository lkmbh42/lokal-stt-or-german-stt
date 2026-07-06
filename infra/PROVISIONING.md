# Offline Provisioning Runbook — Variant B (air-gapped)

Goal: bring the team server up on a host with **no internet access**.
Everything network-dependent happens on a connected build machine; the
target host only ever loads local artifacts.

## 1. On the connected build machine

```bash
git clone <repo> && cd <repo>

# 1a. Build the frontend and the server image
cd apps/server/frontend && npm ci && npm run build && cd ../../..
cd infra && docker compose build api        # same image serves api + worker

# 1b. Export the image
docker save lokal-stt-api | gzip > lokal-stt-image.tar.gz

# 1c. Stage model weights (pick one)
python ../engine/scripts/download_model.py large-v3 --dest models
# or a German fine-tune (convert once, see engine/README.md):
#   ct2-transformers-converter --model primeline/whisper-large-v3-turbo-german \
#       --output_dir models/whisper-large-v3-turbo-german-ct2 \
#       --copy_files tokenizer.json preprocessor_config.json --quantization float16

# 1d. Pull the infrastructure images and export them too
docker pull nginx:1.27-alpine postgres:16-alpine redis:7-alpine
docker save nginx:1.27-alpine postgres:16-alpine redis:7-alpine \
  | gzip > lokal-stt-infra-images.tar.gz
```

Transfer to the target host (USB/one-way gateway):
`lokal-stt-image.tar.gz`, `lokal-stt-infra-images.tar.gz`, the `infra/`
directory (including `models/` and `../apps/server/frontend/dist`).

## 2. On the air-gapped target host

```bash
docker load < lokal-stt-image.tar.gz
docker load < lokal-stt-infra-images.tar.gz

cd infra
cp .env.example .env
# set: STT_SECRET_KEY (openssl rand -hex 32), POSTGRES_PASSWORD,
#      STT_BOOTSTRAP_ADMIN_PASSWORD, STT_ENGINE__MODEL=/models/<staged dir>
# keep: STT_ENGINE__LOCAL_FILES_ONLY=true   <- the air-gap guarantee

# TLS (recommended): certificate from your internal CA as tls/cert.pem +
# tls/key.pem, or self-signed:
./tls/generate-self-signed.sh stt.team.internal
cp nginx/tls.conf.example nginx/default.conf
# then uncomment the 443 port + ./tls volume on the nginx service

docker compose up -d --no-build
curl -k https://localhost:8443/api/health
```

Migrations run automatically on API start. The bootstrap admin is created
on first start only; log in and create team accounts in the admin panel.

## 3. Verification checklist (run once after every deployment)

- [ ] `docker compose ps` — five services up, postgres/redis healthy.
- [ ] `/api/health` returns the staged model path.
- [ ] Upload a short German WAV as a normal user → job completes → export ok.
- [ ] **Egress test:** block/unplug outbound network → repeat the upload —
      must behave identically (`LOCAL_FILES_ONLY=true` means a missing model
      is a hard error, never a download attempt).
- [ ] Audit log shows the login and job events (admin panel).

## 4. Model updates later

Stage the new CTranslate2 directory into `models/` on the build machine,
transfer, update `STT_ENGINE__MODEL` in `.env`, `docker compose restart
worker api`. Nothing else changes; old weights can stay for rollback.

## 5. Backup / restore

State lives in exactly three places:

| What | Where | Backup |
|---|---|---|
| Users, jobs, audit | `pg-data` volume | `docker compose exec postgres pg_dump -U stt stt > backup.sql` |
| Audio + transcripts | `stt-data` volume | `docker run --rm -v lokal-stt_stt-data:/d -v $PWD:/b alpine tar czf /b/stt-data.tar.gz -C /d .` |
| Config/secrets | `infra/.env`, `infra/tls/` | copy files (protect the key material) |

Restore: `docker compose up -d postgres` → `psql -U stt stt < backup.sql` →
untar the data volume → `docker compose up -d`. A full runbook with retention
guidance lands in the Phase 4 final docs.
