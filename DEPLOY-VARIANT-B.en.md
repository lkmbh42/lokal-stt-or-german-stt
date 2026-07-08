# Variant B — Team Server: Deployment & Run, Step by Step

Multi-user server for a small team (~10 people) sharing one GPU/CPU: login,
roles, quotas, audit log, job queue. Runs entirely in Docker (nginx, API,
worker, Postgres, Redis). This guide goes from a blank server to the first
transcript — including the offline/air-gap path.

---

## Part 1 — Prerequisites

On the **server**:

| Software | Check with |
|---|---|
| Docker Engine + Compose plugin (or Docker Desktop) | `docker compose version` |
| git (only if building directly on the server) | `git --version` |

On the **build machine** (can be the same server, if it has internet):
additionally Node.js ≥ 20 and Python ≥ 3.10 (for the frontend build and
model staging).

**GPU server:** additionally install NVIDIA drivers +
`nvidia-container-toolkit` (`nvidia-smi` must work on the host).

---

## Part 2 — Prepare the build (on the machine with internet)

**Step 1 — Get the code:**

```bash
git clone <repo-url> lokal-stt && cd lokal-stt
```

**Step 2 — Build the web frontend** (served by nginx):

```bash
cd apps/server/frontend
npm ci
npm run build
cd ../../..
```

**Step 3 — Stage the model** (mounted into the container as a volume,
never downloaded at runtime):

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .\.venv\Scripts\activate
pip install huggingface_hub
python engine/scripts/download_model.py large-v3 --dest infra/models
```

Result: `infra/models/faster-whisper-large-v3/`.

**Step 4 — Create the config file:**

```bash
cd infra
cp .env.example .env
```

Open `.env` in an editor and set **at minimum**:

```bash
STT_SECRET_KEY=            # generate with:  openssl rand -hex 32
POSTGRES_PASSWORD=         # choose freely, store securely
STT_BOOTSTRAP_ADMIN_USERNAME=admin
STT_BOOTSTRAP_ADMIN_PASSWORD=   # first admin account's password (10+ chars)
STT_ENGINE__MODEL=/models/faster-whisper-large-v3
STT_ENGINE__LOCAL_FILES_ONLY=true
```

**Accuracy:** `large-v3` gives the best quality and belongs on a GPU
server. If the server has **no GPU**, use `large-v3-turbo` instead
(Step 3: `download_model.py large-v3-turbo`, then
`STT_ENGINE__MODEL=/models/faster-whisper-large-v3-turbo`) — near-equal
German accuracy at roughly 4× the speed. Browser recordings are always
transcribed as a complete file with this model.

Optional knobs (defaults are sensible): `STT_HTTP_PORT` (default 8080),
`STT_MAX_CONCURRENT_JOBS` (GPU slots, see Part 5),
`STT_DEFAULT_DAILY_MINUTES` / `STT_DEFAULT_MONTHLY_MINUTES` (default quota,
0 = unlimited), `STT_MAX_UPLOAD_MB`.

**Step 5 — Set up TLS (recommended):**

```bash
./tls/generate-self-signed.sh stt.company.internal   # or drop your internal CA's cert as tls/cert.pem + tls/key.pem
cp nginx/tls.conf.example nginx/default.conf
```

Then in `docker-compose.yml`, uncomment the two commented lines on the
`nginx` service (port `8443:443` and volume `./tls:/etc/nginx/tls:ro`).
Self-signed certificate: import `tls/cert.pem` into client trust stores,
otherwise browsers will warn.

*(Without TLS, the server runs over HTTP on port 8080 — acceptable only on
trusted internal networks.)*

---

## Part 3 — Bring it up

### Path A: the server has internet (or is the build machine)

```bash
cd infra
docker compose up --build -d
```

### Path B: air-gapped (server has no internet)

On the build machine, additionally:

```bash
cd infra
docker compose build
docker save lokal-stt-api lokal-stt-worker | gzip > lokal-stt-image.tar.gz
docker pull nginx:1.27-alpine postgres:16-alpine redis:7-alpine
docker save nginx:1.27-alpine postgres:16-alpine redis:7-alpine | gzip > lokal-stt-infra.tar.gz
```

Transfer to the target server: both `.tar.gz` files, the entire `infra/`
directory (including `models/`, `.env`, `tls/`), and
`apps/server/frontend/dist/` (keep the directory structure — nginx mounts
`../apps/server/frontend/dist`). Then on the target server:

```bash
docker load < lokal-stt-image.tar.gz
docker load < lokal-stt-infra.tar.gz
cd infra
docker compose up -d --no-build
```

Details and a verification checklist:
[infra/PROVISIONING.md](infra/PROVISIONING.md).

### Startup check (both paths)

```bash
docker compose ps                                  # 5 services, postgres/redis "healthy"
curl http://localhost:8080/api/health              # {"status":"ok", ...}
# with TLS: curl -k https://localhost:8443/api/health
```

Database migrations run automatically on API start; the admin account from
`.env` is created on the very first start only.

---

## Part 4 — First steps as a team

1. **Log in:** browser → `http://<server>:8080` (or `https://…:8443`), log
   in with the bootstrap admin from `.env`.
2. **Create users:** "Administration" → "Benutzerverwaltung" (user
   management) → username + password (10+ characters). Optionally set a
   per-user daily minute quota.
3. **Work as a user:** log in → upload an audio file or record directly →
   queue position and estimated wait appear as text → after completion,
   export as txt/srt/vtt/json/docx/zip.
4. **Monitor (admin):** "Systemstatus" shows queue depth, measured
   processing speed, and per-user storage; "Auditprotokoll" (audit log)
   shows logins and all jobs (CSV export available).

### Dictation mode (spoken punctuation)

Tick **"Diktatmodus"** before recording/uploading to speak punctuation
aloud — the only way to get marks Whisper can't hear (parentheses, colons,
semicolons, dashes, quotes). Say the command words in your speech:

| Say | Get | | Say | Get |
|---|---|---|---|---|
| Komma | , | | Klammer auf/zu | ( ) |
| Punkt | . | | eckige Klammer auf/zu | [ ] |
| Fragezeichen | ? | | geschweifte Klammer auf/zu | { } |
| Ausrufezeichen | ! | | Anführungszeichen auf/zu | „ " |
| Doppelpunkt | : | | Gedankenstrich | – |
| Semikolon | ; | | Bindestrich | - |
| Schrägstrich | / | | Paragraf | § |
| Prozentzeichen | % | | Sternchen | * |
| neue Zeile | ⏎ | | neuer Absatz | ⏎⏎ |

Extras: **"großschreiben"** before a word capitalizes it (handy for names —
"…nach großschreiben Cappel"); **"kleinschreiben"** lowercases it. Digits
around a comma become a decimal ("3 Komma 5" → "3,5").

Only the exact singular form is a command, so plural content words survive:
"…mit Doppelpunkt Kommas Semikolon Punkten" → "…mit: Kommas; Punkten". And
your own pauses are handled — Whisper's stray commas around command words are
removed automatically. Leave the mode off for normal speech, where Whisper
infers basic punctuation itself.

---

## Part 5 — Enable GPU (recommended for large-v3)

1. In `docker-compose.yml`, uncomment `gpus: all` on the `worker` service.
2. In `.env`: `STT_ENGINE__DEVICE=cuda`.
3. Size `STT_MAX_CONCURRENT_JOBS` to GPU memory: large-v3 with float16 needs
   ≈ 4.7 GB per concurrent job (a 24 GB GPU can support up to 4; start
   conservatively with 1–2).
4. `docker compose up -d` — then re-run the load test
   ([docs/load-test-phase3.md](docs/load-test-phase3.md)) and document the
   measured numbers.

---

## Part 6 — Operations: the essentials

```bash
docker compose logs -f api worker      # follow logs
docker compose restart worker          # e.g. after a model change
docker compose down                    # stop (data stays in volumes)
docker compose up -d                   # start again
```

- **Backup:** three locations — Postgres dump, `stt-data` volume (audio +
  transcripts), `infra/.env` + `infra/tls/`. Commands:
  [infra/PROVISIONING.md §5](infra/PROVISIONING.md).
- **Applying updates / swapping the model:**
  [docs/runbook-server.md](docs/runbook-server.md) and
  [docs/model-management.md](docs/model-management.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Jobs stuck "queued" | `docker compose logs worker` — usually `STT_ENGINE__MODEL` is wrong or `infra/models/` is missing |
| API won't start, log mentions `secret_key` | `STT_SECRET_KEY` missing from `.env` — deliberately a required field |
| Port 8080 already in use | Set `STT_HTTP_PORT=<other port>` in `.env`, then `docker compose up -d` |
| 429 "Zu viele Anmeldeversuche" (too many login attempts) | Rate limiter working as intended; wait, or raise `STT_AUTH_RATE_LIMIT_ATTEMPTS` (e.g. behind a corporate NAT) |
| Browser warns about the certificate | Import the self-signed `tls/cert.pem` on clients, or use a certificate from your internal CA |
| Upload fails with "Kontingent erschöpft" (quota exhausted) | Intended: daily/monthly limit reached — an admin can adjust it per user |
