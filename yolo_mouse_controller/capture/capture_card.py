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
        idx = self.config.device_index
        print(f"Opening capture device {idx} with MSMF (ultra-low latency)")
        # v2: MSMF 底层加速，替代由于 DirectShow 带来的 2 帧缓冲延时 (Todo 4)
        self.cap = cv2.VideoCapture(idx, cv2.CAP_MSMF)
        if not self.cap.isOpened():
            print(f"MSMF failed, falling back to DSHOW for id={idx}")
            self.cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        # ???????????? OpenCV ?????????????
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
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
