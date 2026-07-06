"""Single-command launcher for the desktop STT tool.

    python run.py                     # start on the configured port, open browser
    python run.py --config config.yaml
    python run.py --port 0            # pick a free port automatically
    python run.py --no-browser        # headless (e.g. started by a service)

Binds to 127.0.0.1 only — this is enforced by config validation, not just a
default. Model weights load lazily on the first job, so startup is instant.
"""

from __future__ import annotations

import argparse
import logging
import socket
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from desktop_app.app import create_app
from desktop_app.config import load_app_config

logger = logging.getLogger("launcher")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def open_browser_when_ready(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1):
                webbrowser.open(url)
                logger.info("Browser geöffnet: %s", url)
                return
        except OSError:
            time.sleep(0.3)
    logger.warning("Server wurde nicht rechtzeitig erreichbar — Browser nicht geöffnet.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lokal-STT Desktop starten")
    parser.add_argument("--config", default=None, help="Pfad zu config.yaml")
    parser.add_argument(
        "--port", type=int, default=None, help="Port (0 = freien Port wählen)"
    )
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht öffnen")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = load_app_config(args.config)
    if args.port is not None:
        port = find_free_port() if args.port == 0 else args.port
        config = config.model_copy(update={"port": port})

    url = f"http://{config.host}:{config.port}"
    print(f"Lokal-STT läuft unter: {url}  (Beenden mit Strg+C)")

    if not args.no_browser:
        threading.Thread(
            target=open_browser_when_ready, args=(url,), daemon=True
        ).start()

    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
