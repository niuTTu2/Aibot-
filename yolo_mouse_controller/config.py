from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CaptureConfig:
    source: str = "dxgi"
    monitor_index: int = 0
    device_index: int = 0
    width: int = 1920
    height: int = 1080
    crop_width: int = 0
    crop_height: int = 0
    fps: int = 60
    region: tuple[int, int, int, int] | None = None


@dataclass
class ModelConfig:
    path: str = "yolov8n.pt"
    imgsz: int | tuple[int, int] = 640
    conf: float = 0.35
    iou: float = 0.45
    device: str | int | None = None


@dataclass
class TargetConfig:
    class_names: list[str] = field(default_factory=list)
    prefer_center: bool = True
    aim_offset_x: float = 0.0
    aim_offset_y: float = 0.0
    max_distance_px: float = 900.0


@dataclass
class MouseConfig:
    enabled: bool = True
    hold_to_move: bool = True
    enable_key: int = 0x06
    sensitivity: float = 0.35
    smoothing: float = 0.55
    deadzone_px: int = 3
    max_step_px: int = 45
    click_enabled: bool = False
    click_key: int = 0x05


@dataclass
class RuntimeConfig:
    preview: bool = False
    preview_scale: float = 0.5
    preview_initial_width: int | None = None
    preview_initial_height: int | None = None
    print_fps: bool = True
    quit_key: str = "q"


@dataclass
class AppConfig:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    target: TargetConfig = field(default_factory=TargetConfig)
    mouse: MouseConfig = field(default_factory=MouseConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


def _merge_dataclass(instance: Any, values: dict[str, Any]) -> Any:
    for key, value in values.items():
        if not hasattr(instance, key):
            raise ValueError(f"Unknown config key: {key}")
        current = getattr(instance, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_dataclass(current, value)
        else:
            setattr(instance, key, value)
    return instance


def load_config(path: str | Path) -> AppConfig:
    import yaml

    cfg = AppConfig()
    with Path(path).open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError("Config file root must be a mapping.")
    return _merge_dataclass(cfg, data)
