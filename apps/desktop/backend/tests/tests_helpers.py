from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

WAV_BYTES = b"RIFF" + b"\x00" * 40 + b"fakepcm" * 100


def upload(
    client: TestClient,
    filename: str,
    content: bytes = WAV_BYTES,
    data: dict[str, str] | None = None,
) -> httpx.Response:
    return client.post(
        "/api/jobs",
        files={"file": (filename, content, "audio/wav")},
        data=data or {},
    )
