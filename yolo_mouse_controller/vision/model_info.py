from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


ImageSize = int | tuple[int, int]


@dataclass(frozen=True)
class ModelInfo:
    classes: list[tuple[int, str]]
    fixed_imgsz: ImageSize | None = None


def read_model_info(path: str | Path) -> ModelInfo:
    classes = read_yolo_classes(path)
    fixed_imgsz = read_onnx_input_size(path)
    return ModelInfo(classes=classes, fixed_imgsz=fixed_imgsz)


def read_yolo_classes(path: str | Path) -> list[tuple[int, str]]:
    from ultralytics import YOLO

    model = YOLO(str(path), task="detect")
    names = getattr(model, "names", None)
    if callable(names):
        names = names()
    if names is None and hasattr(model, "model"):
        names = getattr(model.model, "names", None)

    if isinstance(names, dict):
        parsed = [(int(class_id), str(name)) for class_id, name in names.items()]
        return sorted(parsed, key=lambda item: item[0])
    if isinstance(names, (list, tuple)):
        return [(idx, str(name)) for idx, name in enumerate(names)]
    return []


def read_onnx_input_size(path: str | Path) -> ImageSize | None:
    model_path = Path(path)
    if model_path.suffix.lower() != ".onnx":
        return None

    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 3
    session = ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
    inputs = session.get_inputs()
    if not inputs:
        return None

    shape = inputs[0].shape
    if len(shape) < 4:
        return None

    height = _shape_dim_to_int(shape[2])
    width = _shape_dim_to_int(shape[3])
    if height is None or width is None:
        return None
    if height == width:
        return height
    return (height, width)


def format_imgsz(imgsz: ImageSize) -> str:
    if isinstance(imgsz, tuple):
        return f"{imgsz[0]}x{imgsz[1]}"
    return f"{imgsz}x{imgsz}"


def normalize_imgsz(value: Any) -> ImageSize:
    if isinstance(value, tuple) and len(value) == 2:
        return int(value[0]), int(value[1])
    if isinstance(value, list) and len(value) == 2:
        return int(value[0]), int(value[1])
    return int(value)


def _shape_dim_to_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
