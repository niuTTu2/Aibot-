from __future__ import annotations

from yolo_mouse_controller.config import CaptureConfig

from .base import FrameSource
from .capture_card import CaptureCardSource
from .dxgi import DxgiSource


def create_frame_source(config: CaptureConfig) -> FrameSource:
    source = config.source.lower()
    if source == "dxgi":
        return DxgiSource(config)
    if source in {"capture_card", "card", "camera", "opencv"}:
        return CaptureCardSource(config)
    raise ValueError(f"Unsupported capture source: {config.source}")
