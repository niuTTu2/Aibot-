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
        self.camera.start(region=region, target_fps=self.config.fps, video_mode=True)

    def read(self) -> np.ndarray | None:
        if self.camera is None:
            return None
        return self.camera.get_latest_frame()

    def stop(self) -> None:
        if self.camera is not None:
            self.camera.stop()
            self.camera = None
