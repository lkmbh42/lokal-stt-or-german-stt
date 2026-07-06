from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from desktop_app.config import AppConfig, load_app_config


class TestLoopbackEnforcement:
    def test_default_is_loopback(self) -> None:
        assert AppConfig().host == "127.0.0.1"

    def test_localhost_normalized(self) -> None:
        assert AppConfig(host="localhost").host == "127.0.0.1"

    def test_public_bind_rejected(self) -> None:
        with pytest.raises(ValidationError, match="loopback"):
            AppConfig(host="0.0.0.0")

    def test_lan_bind_rejected(self) -> None:
        with pytest.raises(ValidationError, match="loopback"):
            AppConfig(host="192.168.1.10")


class TestYaml:
    def test_nested_engine_and_live_config(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "port: 9000\n"
            "engine:\n  model: small\n  device: cpu\n"
            "live:\n  tick_seconds: 2.0\n",
            encoding="utf-8",
        )
        config = load_app_config(cfg_file)
        assert config.port == 9000
        assert config.engine.model == "small"
        assert config.live.tick_seconds == 2.0

    def test_none_gives_defaults(self) -> None:
        assert load_app_config(None) == AppConfig()

    def test_dirs_created(self, tmp_path: Path) -> None:
        config = AppConfig(data_dir=tmp_path / "data")
        config.ensure_dirs()
        assert config.uploads_dir.is_dir()
        assert config.transcripts_dir.is_dir()
