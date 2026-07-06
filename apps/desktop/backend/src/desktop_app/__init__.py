"""Variant A — single-user local German STT tool.

A thin FastAPI shell around the shared :mod:`engine` package: localhost-only
HTTP API + WebSocket live transcription + static React frontend. No auth, no
multi-tenancy, no external services — by design.
"""

__version__ = "0.1.0"
