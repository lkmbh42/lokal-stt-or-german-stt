"""The core ASR engine: faster-whisper (CTranslate2) + Silero VAD.

This is the single ``transcribe(audio, config) -> TranscriptResult`` API both
product variants consume — engine logic is never forked between them.

Design notes
------------
* faster-whisper's integrated ``vad_filter`` *is* Silero VAD (running on
  onnxruntime); enabling it pre-segments audio before ASR, which cuts
  hallucinations on silence and skips non-speech entirely.
* The model is loaded lazily and cached; :meth:`Transcriber.swap_model`
  supports config-driven hot-swapping (e.g. switching to a German fine-tuned
  CTranslate2 checkpoint directory) without process restart.
* Language is always forced (``de`` by default). Auto-detection is not
  reachable through this API.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from engine.audio import decode_audio
from engine.config import EngineConfig, TranscribeOptions
from engine.device import resolve_device
from engine.pipeline import build_default_pipeline
from engine.types import Segment, TranscriptInfo, TranscriptResult, Word

if TYPE_CHECKING:  # pragma: no cover
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

AudioInput = str | Path | np.ndarray


class Transcriber:
    """Thread-safe wrapper around a faster-whisper model instance.

    One instance owns one loaded model. Concurrent ``transcribe`` calls are
    serialized with a lock — scheduling across GPU slots is the job of the
    deployment shell (single async slot in Variant A, worker pool in
    Variant B), not the engine.
    """

    def __init__(self, config: EngineConfig):
        self._config = config
        self._model: WhisperModel | None = None
        self._resolved: tuple[str, str] | None = None
        self._lock = threading.Lock()

    @property
    def config(self) -> EngineConfig:
        return self._config

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Load model weights eagerly (otherwise loading happens on first job)."""
        with self._lock:
            self._ensure_model()

    def swap_model(self, model: str) -> None:
        """Hot-swap to a different model name or local CTranslate2 path.

        The old model is released; the new one loads lazily on next use.
        """
        with self._lock:
            self._config = self._config.model_copy(update={"model": model})
            self._model = None
            self._resolved = None
            logger.info("Model swapped to %r (will load on next use).", model)

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            from faster_whisper import WhisperModel

            device, compute_type = resolve_device(
                self._config.device, self._config.compute_type
            )
            logger.info(
                "Loading model %r (device=%s, compute_type=%s, local_files_only=%s)",
                self._config.model,
                device,
                compute_type,
                self._config.local_files_only,
            )
            started = time.perf_counter()
            self._model = WhisperModel(
                self._config.model,
                device=device,
                compute_type=compute_type,
                cpu_threads=self._config.cpu_threads,
                num_workers=self._config.num_workers,
                download_root=(
                    str(self._config.download_root) if self._config.download_root else None
                ),
                local_files_only=self._config.local_files_only,
            )
            self._resolved = (device, compute_type)
            logger.info("Model loaded in %.1fs", time.perf_counter() - started)
        return self._model

    def transcribe(
        self,
        audio: AudioInput,
        options: TranscribeOptions | None = None,
        on_segment: Callable[[Segment], None] | None = None,
    ) -> TranscriptResult:
        """Transcribe a file path or a 16 kHz mono float32 waveform.

        Decoding of compressed containers (mp3/m4a/mp4/flac/wav) happens
        in-process via PyAV (ffmpeg-CLI fallback) — no network.

        ``on_segment`` is invoked with each *raw* segment as inference
        produces it — callers use it for progress reporting
        (``segment.end / info.duration``). An exception raised by the
        callback aborts transcription and propagates, which is the designed
        mechanism for cooperative job cancellation.
        """
        options = options or TranscribeOptions()
        if isinstance(audio, (str, Path)):
            audio_path = Path(audio)
            if not audio_path.is_file():
                raise FileNotFoundError(f"audio file not found: {audio_path}")
            waveform = decode_audio(audio_path)
        else:
            waveform = audio

        with self._lock:
            model = self._ensure_model()
            device, compute_type = self._resolved or ("unknown", "unknown")

            raw_segments, info = model.transcribe(
                waveform,
                language=options.language,
                task=options.task,
                beam_size=options.beam_size,
                temperature=options.temperature,
                initial_prompt=options.initial_prompt,
                hotwords=options.hotwords,
                word_timestamps=options.word_timestamps,
                condition_on_previous_text=options.condition_on_previous_text,
                vad_filter=self._config.vad.enabled,
                vad_parameters=(
                    self._config.vad.to_vad_parameters() if self._config.vad.enabled else None
                ),
            )

            segments: list[Segment] = []
            # materializing the generator runs inference, segment by segment
            for idx, seg in enumerate(raw_segments):
                segment = Segment(
                    id=idx,
                    start=float(seg.start),
                    end=float(seg.end),
                    text=seg.text.strip(),
                    words=[
                        Word(
                            start=float(w.start),
                            end=float(w.end),
                            text=w.word.strip(),
                            probability=float(w.probability),
                        )
                        for w in (seg.words or [])
                    ],
                )
                segments.append(segment)
                if on_segment is not None:
                    on_segment(segment)

        result = TranscriptResult(
            segments=segments,
            info=TranscriptInfo(
                language=info.language,
                language_probability=float(info.language_probability),
                duration=float(info.duration),
                duration_after_vad=_get_float(info, "duration_after_vad"),
                model=self._config.model,
                device=device,
                compute_type=compute_type,
                engine_version=_engine_version(),
            ),
        )
        return build_default_pipeline(options).run(result)


def _get_float(obj: Any, attr: str) -> float | None:
    value = getattr(obj, attr, None)
    return float(value) if value is not None else None


def _engine_version() -> str:
    from engine import __version__

    return __version__
