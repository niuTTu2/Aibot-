from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from yolo_mouse_controller.config import ModelConfig
from yolo_mouse_controller.vision.model_info import format_imgsz, normalize_imgsz, read_onnx_input_size


@dataclass(frozen=True)
class Detection:
    xyxy: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0

    @property
    def width(self) -> float:
        x1, _, x2, _ = self.xyxy
        return x2 - x1

    @property
    def height(self) -> float:
        _, y1, _, y2 = self.xyxy
        return y2 - y1


class YoloDetector:
    def __init__(self, config: ModelConfig) -> None:
        from ultralytics import YOLO

        self.config = config
        self.imgsz = normalize_imgsz(config.imgsz)
        self._apply_fixed_onnx_size()
        self.model = YOLO(config.path, task="detect")

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(
            source=frame,
            imgsz=self.imgsz,
            conf=self.config.conf,
            iou=self.config.iou,
            device=self.config.device,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        names = result.names
        detections: list[Detection] = []
        for box in result.boxes:
            class_id = int(box.cls[0].item())
            xyxy = tuple(float(v) for v in box.xyxy[0].tolist())
            confidence = float(box.conf[0].item())
            detections.append(
                Detection(
                    xyxy=xyxy,
                    confidence=confidence,
                    class_id=class_id,
                    class_name=str(names.get(class_id, class_id)),
                )
            )
        return detections

    def _apply_fixed_onnx_size(self) -> None:
        try:
            fixed_imgsz = read_onnx_input_size(self.config.path)
        except Exception as exc:
            print(f"WARNING: Could not read ONNX input size: {exc}")
            return
        if fixed_imgsz is None or fixed_imgsz == self.imgsz:
            return
        print(
            "ONNX fixed input size detected: "
            f"{format_imgsz(fixed_imgsz)}; overriding configured imgsz={format_imgsz(self.imgsz)}."
        )
        self.imgsz = fixed_imgsz
