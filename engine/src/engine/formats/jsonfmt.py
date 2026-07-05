"""JSON exporter with word-level timestamps.

The schema is versioned so downstream consumers (Variant A/B frontends,
external tooling) can detect breaking changes.
"""

from __future__ import annotations

import json

from engine.types import TranscriptResult

SCHEMA_VERSION = 1


def to_json(result: TranscriptResult) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "info": result.info.model_dump(),
        "text": result.text,
        "segments": [
            {
                "id": seg.id,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "speaker": seg.speaker,
                "words": [
                    {
                        "start": w.start,
                        "end": w.end,
                        "text": w.text,
                        "probability": w.probability,
                    }
                    for w in seg.words
                ],
            }
            for seg in result.segments
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
