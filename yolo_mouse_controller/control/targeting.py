from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from yolo_mouse_controller.config import MouseConfig, TargetConfig
from yolo_mouse_controller.vision import Detection


@dataclass(frozen=True)
class AimStep:
    dx: int
    dy: int
    target: Detection | None


class TargetSelector:
    def __init__(self, target_config: TargetConfig, mouse_config: MouseConfig) -> None:
        self.target_config = target_config
        self.mouse_config = mouse_config
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0

    def select(self, detections: list[Detection], frame_width: int, frame_height: int) -> Detection | None:
        allowed = set(self.target_config.class_names)
        candidates = [
            item
            for item in detections
            if not allowed or item.class_name in allowed or str(item.class_id) in allowed
        ]
        if not candidates:
            return None

        center_x = frame_width / 2.0
        center_y = frame_height / 2.0

        def distance_to_center(item: Detection) -> float:
            x, y = self._aim_point(item)
            return hypot(x - center_x, y - center_y)

        if self.target_config.prefer_center:
            target = min(candidates, key=lambda item: (distance_to_center(item), -item.confidence))
        else:
            target = max(candidates, key=lambda item: (item.confidence, -distance_to_center(item)))

        distance = distance_to_center(target)
        if distance > self.target_config.max_distance_px:
            return None
        return target

    def aim_step(self, target: Detection | None, frame_width: int, frame_height: int) -> AimStep:
        if target is None:
            self._smooth_dx = 0.0
            self._smooth_dy = 0.0
            return AimStep(0, 0, None)

        center_x = frame_width / 2.0
        center_y = frame_height / 2.0
        aim_x, aim_y = self._aim_point(target)
        raw_dx = (aim_x - center_x) * self.mouse_config.sensitivity
        raw_dy = (aim_y - center_y) * self.mouse_config.sensitivity

        alpha = max(0.0, min(1.0, self.mouse_config.smoothing))
        self._smooth_dx = self._smooth_dx * alpha + raw_dx * (1.0 - alpha)
        self._smooth_dy = self._smooth_dy * alpha + raw_dy * (1.0 - alpha)

        dx = self._clamp_step(self._smooth_dx)
        dy = self._clamp_step(self._smooth_dy)
        if abs(dx) <= self.mouse_config.deadzone_px:
            dx = 0
        if abs(dy) <= self.mouse_config.deadzone_px:
            dy = 0
        return AimStep(dx, dy, target)

    def _aim_point(self, detection: Detection) -> tuple[float, float]:
        x1, y1, x2, y2 = detection.xyxy
        x = (x1 + x2) / 2.0 + detection.width * self.target_config.aim_offset_x
        y = (y1 + y2) / 2.0 + detection.height * self.target_config.aim_offset_y
        return x, y

    def _clamp_step(self, value: float) -> int:
        limit = max(1, self.mouse_config.max_step_px)
        return int(max(-limit, min(limit, round(value))))
