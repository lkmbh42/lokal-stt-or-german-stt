from __future__ import annotations

import json
from pathlib import Path

import pytest

import engine.transcribe as cli
from engine.config import EngineConfig, TranscribeOptions
from engine.types import TranscriptResult


class StubTranscriber:
    """Stands in for the real Transcriber; returns the shared sample result."""

    last_instance: StubTranscriber | None = None

    def __init__(self, config: EngineConfig):
        self.config = config
        self.calls: list[tuple[Path, TranscribeOptions]] = []
        StubTranscriber.last_instance = self

    def transcribe(self, audio: Path, options: TranscribeOptions) -> TranscriptResult:
        self.calls.append((audio, options))
        return self._result

    _result: TranscriptResult


@pytest.fixture
def stub(
    monkeypatch: pytest.MonkeyPatch, sample_result: TranscriptResult
) -> type[StubTranscriber]:
    StubTranscriber._result = sample_result
    StubTranscriber.last_instance = None
    monkeypatch.setattr(cli, "Transcriber", StubTranscriber)
    return StubTranscriber


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    path = tmp_path / "sample.wav"
    path.write_bytes(b"RIFF0000WAVE")
    return path


class TestMain:
    def test_default_writes_txt(
        self, stub: type[StubTranscriber], wav: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "out"
        assert cli.main([str(wav), "--lang", "de", "--output-dir", str(out)]) == 0
        assert (out / "sample.txt").read_text(encoding="utf-8").startswith("Guten Tag")

    def test_all_formats(self, stub: type[StubTranscriber], wav: Path, tmp_path: Path) -> None:
        out = tmp_path / "out"
        assert cli.main([str(wav), "--formats", "all", "--output-dir", str(out)]) == 0
        names = {p.name for p in out.iterdir()}
        assert names == {"sample.txt", "sample.srt", "sample.vtt", "sample.json", "sample.docx"}
        payload = json.loads((out / "sample.json").read_text(encoding="utf-8"))
        assert payload["segments"][0]["words"]  # word-level timestamps present

    def test_options_forwarded(
        self, stub: type[StubTranscriber], wav: Path, tmp_path: Path
    ) -> None:
        cli.main(
            [
                str(wav),
                "--output-dir",
                str(tmp_path / "out"),
                "--initial-prompt",
                "Fachbegriffe",
                "--hotwords",
                "Anthropic",
                "--beam-size",
                "2",
                "--model",
                "tiny",
                "--no-vad",
                "--local-files-only",
            ]
        )
        instance = stub.last_instance
        assert instance is not None
        _, options = instance.calls[0]
        assert options.initial_prompt == "Fachbegriffe"
        assert options.hotwords == "Anthropic"
        assert options.beam_size == 2
        assert instance.config.model == "tiny"
        assert instance.config.vad.enabled is False
        assert instance.config.local_files_only is True

    def test_config_file_used(
        self, stub: type[StubTranscriber], wav: Path, tmp_path: Path
    ) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("model: medium\ndevice: cpu\n", encoding="utf-8")
        cli.main([str(wav), "--config", str(cfg), "--output-dir", str(tmp_path / "out")])
        instance = stub.last_instance
        assert instance is not None
        assert instance.config.model == "medium"
        assert instance.config.device == "cpu"

    def test_unknown_format_fails(self, stub: type[StubTranscriber], wav: Path, capsys) -> None:
        assert cli.main([str(wav), "--formats", "pdf"]) == 1
        assert "unknown format" in capsys.readouterr().err


def test_missing_file_reports_error(tmp_path: Path, capsys) -> None:
    # real Transcriber path: nonexistent file fails before any model load
    assert cli.main([str(tmp_path / "nope.wav")]) == 1
    assert "not found" in capsys.readouterr().err
