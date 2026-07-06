"""Run the desktop app: ``python -m desktop_app [--config config.yaml]``."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from desktop_app.app import create_app
from desktop_app.config import load_app_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m desktop_app")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--port", type=int, default=None, help="Override port")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = load_app_config(args.config)
    if args.port is not None:
        config = config.model_copy(update={"port": args.port})

    app = create_app(config)
    # loopback binding is enforced by AppConfig validation
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
