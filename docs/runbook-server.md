# Deployment Runbook — Variant B (Team Server)

Initial installation (incl. air-gap): follow
[infra/PROVISIONING.md](../infra/PROVISIONING.md). This runbook covers
day-2 operations.

## Daily operations

```bash
cd infra
docker compose ps                        # health overview
docker compose logs -f api worker        # follow logs
docker compose restart worker            # e.g. after model change
docker compose down && docker compose up -d   # full restart (queue survives: Postgres)
```

Admin panel (Systemstatus) shows queue depth, measured processing speed,
per-user storage — check it before suspecting infrastructure.

## User management

Everything via the admin panel (or `/api/admin/users`): create users, set
per-user daily/monthly minute quotas (empty = server default from
`STT_DEFAULT_DAILY_MINUTES`/`STT_DEFAULT_MONTHLY_MINUTES`), deactivate
accounts (kills all sessions immediately). The audit log records every
administrative action; export as CSV for compliance.

## Scaling knobs

| Knob | Where | Notes |
|---|---|---|
| `STT_MAX_CONCURRENT_JOBS` | `.env` | = worker concurrency = GPU slots. large-v3 float16 ≈ 4.7 GB VRAM per slot |
| API replicas | `docker compose up -d --scale api=2` | API is stateless; nginx upstream handles it |
| Auth rate limit | `STT_AUTH_RATE_LIMIT_ATTEMPTS` / `..._WINDOW_SECONDS` | per-IP, in-process. If you scale the API wide, move the counters to Redis (see `server_app/ratelimit.py`) |
| Upload cap | `STT_MAX_UPLOAD_MB` | nginx `client_max_body_size` must stay ≥ this |

## Upgrade procedure

```bash
git pull
cd apps/server/frontend && npm ci && npm run build && cd ../../infra
docker compose build
docker compose up -d          # api runs `alembic upgrade head` on start
docker compose ps             # verify healthy
```

Rollback: `git checkout <previous tag>` and repeat. Migrations are additive
so far; check `apps/server/migrations/` before rolling back across a schema
change.

## Backup & restore

State lives in three places — back up all three (see
[PROVISIONING.md §5](../infra/PROVISIONING.md) for the exact commands):

1. **Postgres** (`pg-data`): nightly `pg_dump`, keep ≥ 14 days.
2. **Audio/transcripts** (`stt-data`): tar of the volume, same cadence.
3. **Secrets/config**: `infra/.env`, `infra/tls/` — offline, encrypted.

Restore drill (do this once per quarter): fresh host → PROVISIONING steps →
restore dump + volume → verify a user can log in and export an old
transcript.

## Security operations

- Rotate `STT_SECRET_KEY` to invalidate *all* tokens at once (users must
  re-login): change it in `.env`, `docker compose up -d api`.
- Watch the audit log for `auth.login_failed` bursts and
  `auth.token_replayed` (possible stolen refresh token — deactivate the
  account, which revokes all its sessions, then reactivate with a new
  password).
- Dependency audit cadence: `pip-audit` + `npm audit` per release (CI covers
  tests; audits are run manually or in a scheduled job).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Jobs stuck in "queued" | `docker compose logs worker` — typically model path wrong (`STT_ENGINE__MODEL`) or weights volume not mounted |
| "model not found" + `local_files_only` | Intended air-gap behavior: stage weights, never disable the flag in production |
| 429 on login | Rate limiter — legitimate user behind shared NAT? raise `STT_AUTH_RATE_LIMIT_ATTEMPTS` |
| Uploads fail at ~1 MB | nginx default body size — ensure the provided `default.conf` (512 m) is actually mounted |
| Queue ETA missing | Expected until the first job finishes after worker restart (speed is measured, not guessed) |

Load-test baseline & method: [load-test-phase3.md](load-test-phase3.md) —
re-run after hardware/model changes. Accessibility regression checklist:
[a11y-walkthrough-server.md](a11y-walkthrough-server.md).
