from __future__ import annotations

from yolo_mouse_controller.config import CaptureConfig

from .base import FrameSource
from .capture_card import CaptureCardSource
from .dxgi import DxgiSource


def create_frame_source(config: CaptureConfig) -> FrameSource:
    source = config.source.lower()
    if source == "dxgi":
        raw = DxgiSource(config)
    elif source in {"capture_card", "card", "camera", "opencv"}:
        raw = CaptureCardSource(config)
    else:
        raise ValueError(f"Unsupported capture source: {config.source}")

    from yolo_mouse_controller.capture.base import ThreadedFrameSource
    return ThreadedFrameSource(raw)
