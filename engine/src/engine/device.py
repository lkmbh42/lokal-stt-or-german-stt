"""GPU/CPU detection and compute-type resolution.

Policy (mirrors the project's hard requirement "GPU preferred, automatic CPU
fallback"):

* ``device: auto``  — use CUDA when CTranslate2 reports a device, else CPU.
* ``device: cuda``  — explicit request; unavailable CUDA is a hard error
  (silently falling back would hide a misconfigured production box).
* ``device: cpu``   — always honored.

Compute type ``auto`` resolves to ``float16`` on CUDA and ``int8`` on CPU,
the fastest sensible defaults for faster-whisper on each target.
"""

from __future__ import annotations

import logging

from engine.config import ComputeType, Device

logger = logging.getLogger(__name__)


def cuda_device_count() -> int:
    """Number of visible CUDA devices (0 when CUDA is absent or broken)."""
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:  # pragma: no cover - defensive: broken CUDA runtimes throw
        return 0


def resolve_device(device: Device, compute_type: ComputeType) -> tuple[str, str]:
    """Map requested (device, compute_type) to concrete values.

    Returns a ``(device, compute_type)`` pair accepted by
    ``faster_whisper.WhisperModel``.
    """
    available = cuda_device_count() > 0

    if device == "cuda" and not available:
        raise RuntimeError(
            "device is set to 'cuda' but no CUDA device is available. "
            "Use device: auto for automatic CPU fallback, or fix the CUDA runtime."
        )

    if device == "auto":
        resolved = "cuda" if available else "cpu"
        if not available:
            logger.info("No CUDA device detected — falling back to CPU inference.")
    else:
        resolved = device

    if compute_type == "auto":
        resolved_compute = "float16" if resolved == "cuda" else "int8"
    else:
        resolved_compute = compute_type

    return resolved, resolved_compute
