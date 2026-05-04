from __future__ import annotations

import json
import sys
from pathlib import Path


def _read_torch_info() -> dict[str, object]:
    try:
        import torch
    except Exception as exc:
        return {
            "installed": False,
            "error": str(exc),
            "cuda_available": False,
            "cuda_device_count": 0,
            "devices": [],
        }

    devices: list[dict[str, object]] = []
    cuda_available = bool(torch.cuda.is_available())
    cuda_count = int(torch.cuda.device_count()) if cuda_available else 0
    for i in range(cuda_count):
        name = ""
        try:
            name = str(torch.cuda.get_device_name(i))
        except Exception:
            name = f"CUDA:{i}"
        devices.append({"index": i, "name": name})
    return {
        "installed": True,
        "version": getattr(torch, "__version__", "unknown"),
        "cuda_available": cuda_available,
        "cuda_device_count": cuda_count,
        "devices": devices,
    }


def _read_onnxruntime_info() -> dict[str, object]:
    try:
        import onnxruntime as ort
    except Exception as exc:
        return {"installed": False, "error": str(exc), "providers": []}
    providers = list(ort.get_available_providers())
    return {
        "installed": True,
        "version": getattr(ort, "__version__", "unknown"),
        "providers": providers,
    }


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    torch_info = _read_torch_info()
    ort_info = _read_onnxruntime_info()

    payload = {
        "ok": True,
        "python": sys.version.split()[0],
        "torch": torch_info,
        "onnxruntime": ort_info,
        "device_options": ["auto", "cpu"]
        + [str(item["index"]) for item in torch_info.get("devices", [])],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
