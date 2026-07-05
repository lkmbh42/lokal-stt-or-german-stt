# Variant B — Multi-User Team Server

**Status: not started — gated behind Phases 0–1 (`GO PHASE 2`).**

Planned scope (from the project brief):

- Docker Compose stack: nginx (TLS, static assets), FastAPI API, Celery/RQ
  GPU worker(s) wrapping the shared `engine` package, Postgres, Redis.
- Local auth (Argon2 + JWT) behind a swappable auth interface (LDAP/AD-ready).
- RBAC (`admin` / `user`), strict per-user job isolation with authorization
  tests, server-side quotas, append-only audit log.
- Queue position / ETA surfaced as text in an ARIA live region.
- Air-gap model provisioning: weights baked into the image or mounted from a
  pre-staged volume — never pulled at runtime.

This app consumes the shared [`engine`](../../engine) package — no forked
inference logic.
