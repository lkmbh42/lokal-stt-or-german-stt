# Infrastructure

**Status: not started — populated in Phases 2–3.**

Will contain:

- `docker-compose.yml` + service Dockerfiles for Variant B.
- nginx reverse-proxy and TLS configuration (internal CA / self-signed).
- Offline model export/conversion and image-baking scripts for air-gapped
  deployment (builds on `engine/scripts/download_model.py`).
- Backup/restore procedures for Postgres and the storage volume (Phase 4 docs).
