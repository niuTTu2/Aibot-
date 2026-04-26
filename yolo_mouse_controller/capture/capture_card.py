from __future__ import annotations

import cv2
import numpy as np

from yolo_mouse_controller.config import CaptureConfig

from .base import FrameSource


class CaptureCardSource(FrameSource):
    def __init__(self, config: CaptureConfig) -> None:
        self.config = config
        self.cap: cv2.VideoCapture | None = None

    def start(self) -> None:
        self.cap = cv2.VideoCapture(self.config.device_index, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open capture device {self.config.device_index}.")

    def read(self) -> np.ndarray | None:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        return frame if ok else None

    def stop(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
