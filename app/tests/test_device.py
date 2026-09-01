import pytest
import torch

from app.core.device import resolve_device, resolve_dtype, runtime_status


def test_explicit_cpu_uses_float32_by_default() -> None:
    assert resolve_device("cpu") == "cpu"
    assert resolve_dtype("cpu", "auto") is torch.float32


def test_cpu_rejects_float16() -> None:
    with pytest.raises(ValueError, match="requires CUDA"):
        resolve_dtype("cpu", "float16")


def test_runtime_status_reports_selected_configuration() -> None:
    status = runtime_status("cpu", "auto")
    assert status["configuration_ok"] is True
    assert status["selected_device"] == "cpu"
    assert status["selected_dtype"] == "float32"
