"""Command-line interface.

Usage::

    python -m engine.transcribe sample.wav --lang de
    python -m engine.transcribe meeting.mp3 --formats all --output-dir out
    python -m engine.transcribe interview.m4a --config config.yaml \
        --initial-prompt "Anthropic, Kubernetes, Frau Dr. Weber"

Exit codes: 0 success, 1 transcription/config error, 2 usage error (argparse).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from engine.config import EngineConfig, TranscribeOptions, load_config
from engine.formats import write_outputs
from engine.transcriber import Transcriber
from engine.types import OutputFormat

logger = logging.getLogger(__name__)

_ALL_FORMATS = [f.value for f in OutputFormat]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m engine.transcribe",
        description="Local, offline German speech-to-text (faster-whisper + Silero VAD).",
    )
    parser.add_argument("audio", type=Path, help="Audio file (wav/mp3/m4a/mp4/flac)")
    parser.add_argument("--lang", default="de", help="Transcription language (default: de)")
    parser.add_argument(
        "--config", type=Path, default=None, help="Engine config YAML (see config.example.yaml)"
    )
    parser.add_argument("--model", default=None, help="Model name or local path (overrides config)")
    parser.add_argument(
        "--device", choices=["auto", "cuda", "cpu"], default=None, help="Overrides config"
    )
    parser.add_argument(
        "--formats",
        default="txt",
        help=f"Comma-separated output formats or 'all' ({','.join(_ALL_FORMATS)}); default: txt",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("out"), help="Output directory (default: ./out)"
    )
    parser.add_argument("--initial-prompt", default=None, help="Domain vocabulary priming text")
    parser.add_argument("--hotwords", default=None, help="Hotword boost string")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--no-vad", action="store_true", help="Disable Silero VAD pre-segmentation")
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Hard-offline mode: never download; missing weights are an error",
    )
    parser.add_argument("--download-root", type=Path, default=None, help="Model weights directory")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _parse_formats(spec: str) -> list[OutputFormat]:
    names = _ALL_FORMATS if spec.strip().lower() == "all" else spec.split(",")
    formats: list[OutputFormat] = []
    for name in names:
        name = name.strip().lower()
        if not name:
            continue
        try:
            formats.append(OutputFormat(name))
        except ValueError:
            raise ValueError(
                f"unknown format {name!r}; valid: {', '.join(_ALL_FORMATS)} or 'all'"
            ) from None
    if not formats:
        raise ValueError("no output formats requested")
    return formats


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        formats = _parse_formats(args.formats)
        config = load_config(args.config) if args.config else EngineConfig()

        overrides: dict[str, object] = {}
        if args.model:
            overrides["model"] = args.model
        if args.device:
            overrides["device"] = args.device
        if args.local_files_only:
            overrides["local_files_only"] = True
        if args.download_root:
            overrides["download_root"] = args.download_root
        if args.no_vad:
            overrides["vad"] = config.vad.model_copy(update={"enabled": False})
        if overrides:
            config = config.model_copy(update=overrides)

        options = TranscribeOptions(
            language=args.lang,
            beam_size=args.beam_size,
            initial_prompt=args.initial_prompt,
            hotwords=args.hotwords,
        )

        started = time.perf_counter()
        result = Transcriber(config).transcribe(args.audio, options)
        elapsed = time.perf_counter() - started

        written = write_outputs(result, formats, args.output_dir, args.audio.stem)

        print(
            f"Transcribed {args.audio.name}: {result.info.duration:.1f}s audio, "
            f"{len(result.segments)} segment(s), language={result.info.language}, "
            f"device={result.info.device}/{result.info.compute_type}, "
            f"took {elapsed:.1f}s"
        )
        for path in written:
            print(f"  -> {path}")
        return 0
    except Exception as exc:
        logger.debug("traceback", exc_info=True)
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
