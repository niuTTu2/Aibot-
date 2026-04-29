from __future__ import annotations

import numpy as np

from yolo_mouse_controller.config import CaptureConfig

from .base import FrameSource


class DxgiSource(FrameSource):
    def __init__(self, config: CaptureConfig) -> None:
        self.config = config
        self.camera = None

    def start(self) -> None:
        try:
            import dxcam
        except ImportError as exc:
            raise RuntimeError("DXGI capture requires dxcam. Install it with: pip install dxcam") from exc

        self.camera = dxcam.create(output_idx=self.config.monitor_index, output_color="BGR")
        region = tuple(self.config.region) if self.config.region else None
        if region is None:
            # ????? dxcam ?????????????? UI ?? width/height?
            # UI ? width/height ??????????????????????? DXGI region ??????????????
            region = self._center_region(self.camera.width, self.camera.height)
        # ??? DXGI ???????????????? Python ???????????????
        self.camera.start(region=region, target_fps=self.config.fps, video_mode=True)

    def _center_region(self, src_w: int, src_h: int) -> tuple[int, int, int, int] | None:
        crop_w = int(self.config.crop_width or 0)
        crop_h = int(self.config.crop_height or 0)
        src_w = int(src_w or 0)
        src_h = int(src_h or 0)
        if crop_w <= 0 and crop_h <= 0:
            return None
        if src_w <= 0 or src_h <= 0:
            return None
        crop_w = min(src_w, crop_w if crop_w > 0 else src_w)
        crop_h = min(src_h, crop_h if crop_h > 0 else src_h)
        left = max(0, (src_w - crop_w) // 2)
        top = max(0, (src_h - crop_h) // 2)
        return (left, top, left + crop_w, top + crop_h)

    def read(self) -> np.ndarray | None:
        if self.camera is None:
            return None
        return self.camera.get_latest_frame()

    def stop(self) -> None:
        if self.camera is not None:
            self.camera.stop()
            self.camera = None
