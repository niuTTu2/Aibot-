from __future__ import annotations

import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO


def main() -> int:
    devices: list[dict[str, object]] = [
        {"label": "Auto", "value": "", "kind": "auto", "available": True},
        {"label": "CPU", "value": "cpu", "kind": "cpu", "available": True},
    ]
    notes: list[str] = []

    try:
        noise = StringIO()
        with redirect_stdout(noise), redirect_stderr(noise):
            import torch

        cuda_available = bool(torch.cuda.is_available())
        cuda_count = int(torch.cuda.device_count()) if cuda_available else 0
        for index in range(cuda_count):
            name = torch.cuda.get_device_name(index)
            devices.append(
                {
                    "label": f"CUDA {index}: {name}",
                    "value": str(index),
                    "kind": "cuda",
                    "available": True,
                }
            )
        if not cuda_available:
            notes.append("PyTorch CUDA is not available; PT models will use CPU unless a CUDA-enabled torch build is installed.")
    except Exception as exc:
        notes.append(f"PyTorch scan failed: {exc}")

    try:
        noise = StringIO()
        with redirect_stdout(noise), redirect_stderr(noise):
            import onnxruntime as ort

        providers = list(ort.get_available_providers())
        for provider in providers:
            if provider == "CUDAExecutionProvider":
                devices.append(
                    {
                        "label": "ONNX Runtime CUDA Provider",
                        "value": "0",
                        "kind": "onnx_cuda",
                        "available": True,
                    }
                )
            elif provider == "DmlExecutionProvider":
                devices.append(
                    {
                        "label": "ONNX Runtime DirectML Provider",
                        "value": "dml",
                        "kind": "onnx_dml",
                        "available": True,
                    }
                )
        if "CUDAExecutionProvider" not in providers and "DmlExecutionProvider" not in providers:
            notes.append(
                "ONNX Runtime GPU provider is not available; ONNX models will use CPUExecutionProvider."
            )
        notes.append("ONNX Runtime providers: " + ", ".join(providers))
    except Exception as exc:
        notes.append(f"ONNX Runtime scan failed: {exc}")

    print(json.dumps({"ok": True, "devices": devices, "notes": notes}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
