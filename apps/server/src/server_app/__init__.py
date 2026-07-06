"""Variant B — multi-user team server.

Same shared :mod:`engine` core as the desktop tool, deployed as a Docker
Compose stack: nginx → FastAPI API (stateless) → Redis/Celery → GPU worker,
with Postgres for users/jobs. ~10 concurrent users, one shared GPU.
"""

__version__ = "0.1.0"
