"""Local, offline German speech-to-text engine.

Public API::

    from engine import EngineConfig, TranscribeOptions, Transcriber

    engine = Transcriber(EngineConfig(model="large-v3"))
    result = engine.transcribe("meeting.mp3", TranscribeOptions())
    print(result.text)
"""

from engine.config import EngineConfig, TranscribeOptions, VadConfig, load_config
from engine.transcriber import Transcriber
from engine.types import Segment, TranscriptInfo, TranscriptResult, Word

__all__ = [
    "EngineConfig",
    "TranscribeOptions",
    "VadConfig",
    "load_config",
    "Transcriber",
    "TranscriptResult",
    "TranscriptInfo",
    "Segment",
    "Word",
]

__version__ = "0.1.0"
