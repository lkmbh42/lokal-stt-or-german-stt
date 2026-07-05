"""Stage model weights for air-gapped deployment.

Run this ON A CONNECTED MACHINE, then transfer the destination directory to
the air-gapped host (or bake it into the Docker image in Phase 2/3):

    python engine/scripts/download_model.py large-v3 --dest ./models
    python engine/scripts/download_model.py --dest ./models \
        --repo primeline/whisper-large-v3-turbo-german-ct2

Then point the engine at the staged directory and lock it down::

    model: ./models/faster-whisper-large-v3
    local_files_only: true

Non-CTranslate2 checkpoints (plain HF transformers Whisper fine-tunes) must
be converted first — see engine/README.md, "German fine-tuned checkpoints".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Official CTranslate2 conversions used by faster-whisper.
KNOWN_MODELS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "size",
        nargs="?",
        choices=sorted(KNOWN_MODELS),
        help="Whisper size to stage (mutually exclusive with --repo)",
    )
    parser.add_argument(
        "--repo", default=None, help="Explicit HuggingFace repo id of a CTranslate2 model"
    )
    parser.add_argument("--dest", type=Path, default=Path("models"), help="Destination directory")
    args = parser.parse_args(argv)

    if bool(args.size) == bool(args.repo):
        parser.error("specify exactly one of: a model size, or --repo <hf-repo-id>")

    repo_id = KNOWN_MODELS[args.size] if args.size else args.repo
    target = args.dest / (f"faster-whisper-{args.size}" if args.size else repo_id.split("/")[-1])

    from huggingface_hub import snapshot_download

    print(f"staging {repo_id} -> {target}")
    snapshot_download(
        repo_id,
        local_dir=str(target),
        allow_patterns=["*.bin", "*.json", "*.txt", "*model*", "tokenizer*", "vocabulary*"],
    )
    print("done. Engine config for the air-gapped host:")
    print(f"  model: {target.as_posix()}")
    print("  local_files_only: true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
