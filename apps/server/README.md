# Variant B — Multi-User Team Server

Multi-user German STT for a small team (~10 users) sharing one server/GPU.
Same [`engine`](../../engine) core as the desktop tool — this app adds auth,
per-user isolation and a queue, nothing about inference is forked.

## Run (Docker Compose)

```bash
cd infra
cp .env.example .env            # set STT_SECRET_KEY, POSTGRES_PASSWORD, admin password
python ../engine/scripts/download_model.py large-v3 --dest models
docker compose up --build -d    # nginx on :${STT_HTTP_PORT:-8080}
```

Air-gap: build the image on a connected machine (`docker save`/`docker load`
to transfer), stage weights into `infra/models/`, keep
`STT_ENGINE__LOCAL_FILES_ONLY=true` (default in `.env.example`) — runtime
network egress can be blocked with zero functional loss.

## Architecture

```
nginx  ──►  api (FastAPI, stateless)  ──►  postgres (users, jobs)
                     │ enqueue                ▲
                     ▼                        │ status/progress
             redis (Celery broker)  ──►  worker (Celery, owns the engine/GPU)
```

- The **worker** holds the single engine instance; `STT_MAX_CONCURRENT_JOBS`
  = Celery concurrency = GPU slots (large-v3 float16 ≈ 4.7 GB VRAM each).
  API replicas never load model weights.
- Job state lives in **Postgres** (Celery results are disabled) — the queue
  survives worker restarts, `alembic upgrade head` runs on API start.
- **Queue position** is computed across all users (one shared GPU) and
  returned as text-friendly data for the Phase 3 UI live region.

## Auth & isolation

- **Login** `POST /api/auth/login` → JWT access (15 min) + refresh (7 d,
  rotated on use). Argon2id password hashes. Bootstrap admin from env on
  first start.
- **Swappable backend**: the app depends only on
  `AuthBackend.authenticate(session, username, password)` —
  [auth/backend.py](src/server_app/auth/backend.py) documents the LDAP/AD
  bind implementation sketch. Tokens/RBAC/isolation are unaffected by a swap.
- **RBAC**: `admin` (user management, all-jobs overview) vs `user` (own jobs
  only). Deactivating a user locks them out on their *next request*, not
  their next login.
- **Isolation invariants** (each covered by tests in
  [tests/test_authz_isolation.py](tests/test_authz_isolation.py)):
  - every job query filters `user_id`; foreign job ids return **404**,
    byte-identical to missing ids (no existence oracle);
  - storage paths are per-user (`/data/users/<id>/…`);
  - all `/api/admin/*` routes require the admin role (403).

## API summary

| Route | Auth | Purpose |
|---|---|---|
| `POST /api/auth/login`, `/refresh`, `GET /me` | – / refresh / access | Tokens, whoami |
| `POST /api/jobs` (multipart) | user | Upload; returns queue position |
| `GET /api/jobs`, `GET/DELETE /api/jobs/{id}` | user | Own jobs; delete = cancel when running |
| `GET /api/jobs/{id}/export?format=txt\|srt\|vtt\|json\|docx\|all` | user | Download transcript |
| `GET/POST /api/admin/users`, `PATCH /api/admin/users/{id}` | admin | User management |
| `GET /api/admin/jobs` | admin | All jobs with owners |

## Known tradeoffs (explicit)

- **No refresh-token denylist yet** — a stolen refresh token is valid until
  expiry (7 d default). Mitigated by rotation + live `is_active` checks;
  denylist is on the Phase 4 security-pass list.
- **Auth rate limiting** is scheduled for Phase 4 (per brief).
- **TLS** terminates in Phase 3 (nginx config prepared); until then the
  stack is HTTP-only and must stay on a trusted network.

## Tests

```bash
pip install -e ./engine -e "./apps/server[dev]"
pytest apps/server/tests        # 35 tests: auth, tokens, RBAC, isolation, worker
```

Migrations: `alembic upgrade head` (uses `STT_DATABASE_URL`); CI also runs
`alembic check` against real Postgres to prevent model/migration drift.
