"""PyTorch device selection shared by local model loaders and health checks."""

from typing import Any


def resolve_device(requested: str = "auto") -> str:
    import torch

    value = requested.strip().lower()
    if value not in {"auto", "cpu", "cuda"}:
        raise ValueError("MODEL_DEVICE must be auto, cpu or cuda")
    if value == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("MODEL_DEVICE=cuda but PyTorch cannot access an NVIDIA GPU")
    return "cuda" if value == "cuda" or (value == "auto" and torch.cuda.is_available()) else "cpu"


def resolve_dtype(device: str, requested: str = "auto") -> Any:
    import torch

    value = requested.strip().lower()
    allowed = {"auto", "float32", "float16", "bfloat16"}
    if value not in allowed:
        raise ValueError("MODEL_DTYPE must be auto, float32, float16 or bfloat16")
    if value == "auto":
        if device == "cpu":
            return torch.float32
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    dtype = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}[value]
    if device == "cpu" and dtype == torch.float16:
        raise ValueError("float16 local inference requires CUDA; use float32 on CPU")
    return dtype


def configure_torch(device: str) -> None:
    import torch

    torch.set_float32_matmul_precision("high")
    if device == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True


def runtime_status(requested_device: str = "auto", requested_dtype: str = "auto") -> dict[str, Any]:
    try:
        import torch

        available = torch.cuda.is_available()
        status: dict[str, Any] = {
            "engine": "pytorch-transformers",
            "torch_version": torch.__version__,
            "cuda_build": torch.version.cuda,
            "cuda_available": available,
            "device_count": torch.cuda.device_count() if available else 0,
            "requested_device": requested_device,
            "requested_dtype": requested_dtype,
        }
        if available:
            status.update(
                device_name=torch.cuda.get_device_name(0),
                compute_capability=".".join(map(str, torch.cuda.get_device_capability(0))),
                bf16_supported=torch.cuda.is_bf16_supported(),
                memory_total_mb=round(torch.cuda.get_device_properties(0).total_memory / 1024**2),
            )
        try:
            selected_device = resolve_device(requested_device)
            selected_dtype = resolve_dtype(selected_device, requested_dtype)
            status.update(
                configuration_ok=True,
                selected_device=selected_device,
                selected_dtype=str(selected_dtype).removeprefix("torch."),
            )
        except (RuntimeError, ValueError) as exc:
            status.update(configuration_ok=False, configuration_error=str(exc))
        return status
    except Exception as exc:
        return {
            "engine": "unavailable",
            "cuda_available": False,
            "configuration_ok": False,
            "error": str(exc),
        }
