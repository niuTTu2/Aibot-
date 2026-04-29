from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ImageSize = int | tuple[int, int]
TRT_SUFFIXES = {".engine", ".trt", ".plan", ".rtr"}


@dataclass(frozen=True)
class ModelInfo:
    classes: list[tuple[int, str]]
    fixed_imgsz: ImageSize | None = None


def read_model_info(path: str | Path) -> ModelInfo:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in TRT_SUFFIXES:
        # TensorRT engine ??????? Ultralytics names ????
        # ??????? .names/.txt/.yaml/.json/.onnx ???????
        fixed_imgsz = _read_trt_input_size(p) or _read_sidecar_input_size(p) or _infer_imgsz_from_name(p)
        return ModelInfo(classes=read_trt_sidecar_classes(p), fixed_imgsz=fixed_imgsz)

    classes = read_yolo_classes(path)
    fixed_imgsz = read_onnx_input_size(path)
    return ModelInfo(classes=classes, fixed_imgsz=fixed_imgsz)


def read_yolo_classes(path: str | Path) -> list[tuple[int, str]]:
    p = Path(path)
    if p.suffix.lower() == ".onnx":
        names = _read_onnx_names(p)
        if names:
            return names

    from ultralytics import YOLO

    model = YOLO(str(path), task="detect")
    names = getattr(model, "names", None)
    if callable(names):
        names = names()
    if names is None and hasattr(model, "model"):
        names = getattr(model.model, "names", None)

    return _names_to_classes(names)


def read_trt_sidecar_classes(path: str | Path) -> list[tuple[int, str]]:
    engine_path = Path(path)

    # 1) ??/???????
    for candidate in _sidecar_candidates(engine_path, (".names", ".txt", ".yaml", ".yml", ".json")):
        classes = _read_classes_file(candidate)
        if classes:
            return classes

    # 2) ?? ONNX ??????? xxx_fp16.trt -> xxx_fp16.onnx
    onnx_path = engine_path.with_suffix(".onnx")
    if onnx_path.exists():
        classes = _read_onnx_names(onnx_path)
        if classes:
            return classes
        try:
            return read_yolo_classes(onnx_path)
        except Exception:
            pass

    # 3) ????????????????? ONNX/PT
    for sibling in _related_model_candidates(engine_path):
        try:
            classes = read_yolo_classes(sibling)
            if classes:
                return classes
        except Exception:
            continue
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


def _names_to_classes(names: object) -> list[tuple[int, str]]:
    if isinstance(names, str):
        names = _parse_names_value(names)
    if isinstance(names, dict):
        parsed = [(int(class_id), str(name)) for class_id, name in names.items()]
        return sorted(parsed, key=lambda item: item[0])
    if isinstance(names, (list, tuple)):
        return [(idx, str(name)) for idx, name in enumerate(names)]
    return []


def _parse_names_value(value: str) -> object:
    text = value.strip()
    if not text:
        return None
    try:
        return ast.literal_eval(text)
    except Exception:
        pass
    try:
        return json.loads(text)
    except Exception:
        pass
    return [line.strip() for line in text.splitlines() if line.strip()]


def _read_onnx_names(path: Path) -> list[tuple[int, str]]:
    metadata: dict[str, str] = {}

    # onnx.load ?? metadata_props ??? ORT session ????????
    try:
        import onnx
        model = onnx.load(str(path), load_external_data=False)
        metadata = {prop.key: prop.value for prop in model.metadata_props}
    except Exception:
        metadata = {}

    if not metadata:
        try:
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.log_severity_level = 3
            session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
            metadata = dict(session.get_modelmeta().custom_metadata_map or {})
        except Exception:
            metadata = {}

    for key in ("names", "classes", "class_names", "labels"):
        if key in metadata:
            classes = _names_to_classes(metadata[key])
            if classes:
                return classes
    return []


def _sidecar_candidates(path: Path, suffixes: tuple[str, ...]):
    seen: set[Path] = set()
    stems = [path.stem]
    # ??????xxx_640_fp16.trt?????????? xxx.names
    simplified = re.sub(r"(?:_?fp16|_?fp32|_?int8|_?half|_?trt|_?engine)$", "", path.stem, flags=re.I)
    simplified = re.sub(r"_\d{3,4}$", "", simplified)
    if simplified and simplified not in stems:
        stems.append(simplified)
    for stem in stems:
        for suffix in suffixes:
            candidate = path.with_name(stem + suffix)
            if candidate not in seen and candidate.exists():
                seen.add(candidate)
                yield candidate


def _read_classes_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except UnicodeDecodeError:
        text = path.read_text(encoding="gbk", errors="ignore").strip()
    except Exception:
        return []
    if not text:
        return []

    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            data = json.loads(text)
            if isinstance(data, dict):
                data = data.get("names") or data.get("classes") or data.get("class_names") or data
            return _names_to_classes(data)
        if suffix in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                data = data.get("names") or data.get("classes") or data.get("class_names") or data
            return _names_to_classes(data)
    except Exception:
        pass

    return _names_to_classes([line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")])


def _related_model_candidates(path: Path):
    if not path.parent.exists():
        return []
    base = re.sub(r"(?:_?fp16|_?fp32|_?int8|_?half|_?trt|_?engine)$", "", path.stem, flags=re.I)
    base = re.sub(r"_\d{3,4}$", "", base)
    candidates = []
    for suffix in (".onnx", ".pt"):
        for item in path.parent.glob("*" + suffix):
            if item.stem == path.stem or item.stem.startswith(base) or base.startswith(item.stem):
                candidates.append(item)
    return candidates


def _read_sidecar_input_size(path: Path) -> ImageSize | None:
    onnx_path = path.with_suffix(".onnx")
    if onnx_path.exists():
        return read_onnx_input_size(onnx_path)
    for candidate in _related_model_candidates(path):
        if candidate.suffix.lower() == ".onnx":
            size = read_onnx_input_size(candidate)
            if size:
                return size
    return None


def _infer_imgsz_from_name(path: Path) -> ImageSize | None:
    # xiaohuamaoV8_640_fp16.trt -> 640
    matches = [int(m) for m in re.findall(r"(?<!\d)(\d{3,4})(?!\d)", path.stem)]
    for value in matches:
        if 128 <= value <= 4096 and value % 8 == 0:
            return value
    return None


def _read_trt_input_size(path: Path) -> ImageSize | None:
    """Read input H/W from a TensorRT engine's first input binding."""
    try:
        import tensorrt as trt
        logger = trt.Logger(trt.Logger.ERROR)
        runtime = trt.Runtime(logger)
        with open(path, "rb") as f:
            engine = runtime.deserialize_cuda_engine(f.read())
        if engine is None:
            return None

        # TensorRT 10+ API
        if hasattr(engine, "num_io_tensors"):
            for i in range(engine.num_io_tensors):
                name = engine.get_tensor_name(i)
                if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                    shape = tuple(engine.get_tensor_shape(name))
                    if len(shape) >= 4:
                        h, w = int(shape[2]), int(shape[3])
                        return h if h == w else (h, w)

        # TensorRT 8/9 compatibility API
        for i in range(getattr(engine, "num_bindings", 0)):
            if engine.binding_is_input(i):
                shape = tuple(engine.get_binding_shape(i))
                if len(shape) >= 4:
                    h, w = int(shape[2]), int(shape[3])
                    return h if h == w else (h, w)
    except Exception:
        pass
    return None
