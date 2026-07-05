from __future__ import annotations

import pytest

import engine.device as device_mod
from engine.device import resolve_device


@pytest.fixture
def with_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device_mod, "cuda_device_count", lambda: 1)


@pytest.fixture
def without_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device_mod, "cuda_device_count", lambda: 0)


class TestAutoDevice:
    def test_auto_prefers_cuda(self, with_cuda: None) -> None:
        assert resolve_device("auto", "auto") == ("cuda", "float16")

    def test_auto_falls_back_to_cpu(self, without_cuda: None) -> None:
        assert resolve_device("auto", "auto") == ("cpu", "int8")


class TestExplicitDevice:
    def test_explicit_cuda_without_gpu_is_hard_error(self, without_cuda: None) -> None:
        with pytest.raises(RuntimeError, match="cuda"):
            resolve_device("cuda", "auto")

    def test_explicit_cpu_always_honored(self, with_cuda: None) -> None:
        assert resolve_device("cpu", "auto") == ("cpu", "int8")


class TestComputeType:
    def test_explicit_compute_type_passes_through(self, without_cuda: None) -> None:
        assert resolve_device("cpu", "float32") == ("cpu", "float32")

    def test_explicit_compute_type_on_cuda(self, with_cuda: None) -> None:
        assert resolve_device("auto", "int8_float16") == ("cuda", "int8_float16")


def test_cuda_device_count_returns_int() -> None:
    # Runs against the real ctranslate2 install; must never raise.
    assert isinstance(device_mod.cuda_device_count(), int)
