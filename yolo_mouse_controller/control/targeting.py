from __future__ import annotations

from dataclasses import dataclass
from math import hypot, sqrt

import numpy as np

from yolo_mouse_controller.config import MouseConfig, TargetConfig
from yolo_mouse_controller.vision import Detection


@dataclass(frozen=True)
class AimStep:
    dx: int
    dy: int
    target: Detection | None


class _KalmanTracker:
    """2D constant-velocity Kalman filter with innovation gate for sudden-move recovery."""

    def __init__(self, process_noise: float = 8.0, measure_noise: float = 4.0, gate_sigma: float = 4.0) -> None:
        self._x = np.zeros(4, dtype=np.float64)
        self._P = np.eye(4, dtype=np.float64) * 500.0
        self._F = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float64)
        self._H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float64)
        self._Q = np.eye(4, dtype=np.float64) * process_noise
        self._R = np.eye(2, dtype=np.float64) * measure_noise
        self._gate_sigma = gate_sigma
        self._initialized = False
        self._miss_count = 0

    def reset(self) -> None:
        self._initialized = False
        self._miss_count = 0
        self._P = np.eye(4, dtype=np.float64) * 500.0

    def update(self, x: float, y: float) -> tuple[float, float]:
        if not self._initialized:
            self._x[:] = [x, y, 0.0, 0.0]
            self._initialized = True
            self._miss_count = 0
            return x, y

        self._miss_count = 0

        # Predict
        x_pred = self._F @ self._x
        P_pred = self._F @ self._P @ self._F.T + self._Q

        # Innovation gate: if measurement jumps too far, snap position but preserve velocity direction
        z = np.array([x, y], dtype=np.float64)
        innov = z - self._H @ x_pred
        S = self._H @ P_pred @ self._H.T + self._R
        # Mahalanobis distance squared
        try:
            S_inv = np.linalg.inv(S)
            mahal_sq = float(innov @ S_inv @ innov)
        except np.linalg.LinAlgError:
            mahal_sq = 0.0

        gate_sq = self._gate_sigma ** 2
        if mahal_sq > gate_sq:
            # Target jumped: snap position to measurement, keep velocity, reset covariance
            self._x[0] = x
            self._x[1] = y
            # Decay velocity toward zero to avoid runaway prediction
            self._x[2] *= 0.3
            self._x[3] *= 0.3
            self._P = np.eye(4, dtype=np.float64) * 500.0
            return x, y

        # Normal Kalman update
        K = P_pred @ self._H.T @ S_inv
        self._x = x_pred + K @ innov
        self._P = (np.eye(4) - K @ self._H) @ P_pred

        # Predict one frame ahead
        x_next = self._x[0] + self._x[2]
        y_next = self._x[1] + self._x[3]
        return float(x_next), float(y_next)

    def predict_miss(self) -> tuple[float, float] | None:
        if not self._initialized:
            return None
        self._miss_count += 1
        if self._miss_count > 4:
            self.reset()
            return None
        self._x = self._F @ self._x
        self._P = self._F @ self._P @ self._F.T + self._Q
        return float(self._x[0]), float(self._x[1])

    @property
    def velocity(self) -> tuple[float, float]:
        return float(self._x[2]), float(self._x[3])


def _bbox_iou(a: Detection, b: Detection) -> float:
    """Intersection-over-union for target locking."""
    ax1, ay1, ax2, ay2 = a.xyxy
    bx1, by1, bx2, by2 = b.xyxy
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0.0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


class TargetSelector:
    def __init__(self, target_config: TargetConfig, mouse_config: MouseConfig) -> None:
        self.target_config = target_config
        self.mouse_config = mouse_config
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0
        self._residual_dx = 0.0
        self._residual_dy = 0.0
        self._kalman = _KalmanTracker(
            process_noise=mouse_config.kalman_process_noise,
            measure_noise=mouse_config.kalman_measure_noise,
            gate_sigma=mouse_config.kalman_gate_sigma,
        )
        self._prev_error_x = 0.0
        self._prev_error_y = 0.0
        self._in_deadzone = False
        # Target locking state
        self._locked: Detection | None = None
        self._lock_miss = 0

    def select(self, detections: list[Detection], frame_width: int, frame_height: int) -> Detection | None:
        allowed = set(self.target_config.class_names)
        candidates = [
            item
            for item in detections
            if not allowed or item.class_name in allowed or str(item.class_id) in allowed
        ]
        if not candidates:
            # ?????????????????????????/???????????????
            # ?????????????????????????????????????????????
            self._lock_miss += 1
            if self._lock_miss > self.mouse_config.lock_miss_frames:
                self._locked = None
            return None

        center_x = frame_width / 2.0
        center_y = frame_height / 2.0

        def dist_to_center(item: Detection) -> float:
            x, y = self._aim_point(item)
            return hypot(x - center_x, y - center_y)

        # Try to re-acquire locked target by IoU overlap
        if self.mouse_config.lock_target and self._locked is not None:
            best_iou = 0.0
            best_match: Detection | None = None
            for c in candidates:
                iou = _bbox_iou(self._locked, c)
                if iou > best_iou:
                    best_iou = iou
                    best_match = c
            if best_iou >= 0.15:
                self._locked = best_match
                self._lock_miss = 0
                target = best_match
            else:
                # Small/far targets jitter a lot; IoU can be 0 even for the same target.
                # Use nearest center around the previous locked aim point before giving up.
                lx, ly = self._aim_point(self._locked)

                def lock_center_dist(item: Detection) -> float:
                    x, y = self._aim_point(item)
                    return hypot(x - lx, y - ly)

                center_match = min(candidates, key=lock_center_dist)
                gate = max(36.0, min(120.0, max(self._locked.width, self._locked.height) * 2.8))
                if lock_center_dist(center_match) <= gate:
                    self._locked = center_match
                    self._lock_miss = 0
                    target = center_match
                else:
                    self._locked = None
                    self._lock_miss = 0
                    target = self._fresh_select(candidates, center_x, center_y, dist_to_center)
        else:
            target = self._fresh_select(candidates, center_x, center_y, dist_to_center)

        if target is None:
            return None
        if dist_to_center(target) > self.target_config.max_distance_px:
            self._locked = None
            return None

        if self.mouse_config.lock_target:
            self._locked = target
            self._lock_miss = 0
        return target

    def _fresh_select(self, candidates, center_x, center_y, dist_fn) -> Detection | None:
        if not candidates:
            return None
        if self.target_config.prefer_center:
            return min(candidates, key=lambda item: (dist_fn(item), -item.confidence))
        return max(candidates, key=lambda item: (item.confidence, -dist_fn(item)))

    def aim_step(self, target: Detection | None, frame_width: int, frame_height: int) -> AimStep:
        mode = str(self.mouse_config.movement_mode or "adaptive").lower()
        if mode == "adaptive":
            return self._aim_adaptive(target, frame_width, frame_height)
        return self._aim_legacy(target, frame_width, frame_height, mode)

    # ------------------------------------------------------------------
    # Adaptive PD + Kalman mode
    # ------------------------------------------------------------------

    def _aim_adaptive(self, target: Detection | None, frame_width: int, frame_height: int) -> AimStep:
        center_x = frame_width / 2.0
        center_y = frame_height / 2.0

        if target is None:
            self._kalman.reset()
            self._reset_state()
            return AimStep(0, 0, None)

        raw_x, raw_y = self._aim_point(target)
        aim_x, aim_y = self._kalman.update(raw_x, raw_y)

        error_x = aim_x - center_x
        error_y = aim_y - center_y
        dist = hypot(error_x, error_y)

        deadzone = max(0, int(self.mouse_config.deadzone_px))
        if dist <= deadzone:
            self._reset_state()
            return AimStep(0, 0, target)

        max_step = max(1, int(self.mouse_config.max_step_px))
        max_dist = max(frame_width, frame_height) * 0.5

        # Stable adaptive P control.
        t = min(dist / max(max_dist, 1.0), 1.0)
        curve = max(0.1, float(self.mouse_config.kp_curve))
        kp_hi = float(self.mouse_config.kp)
        kp_lo = float(self.mouse_config.kp_min)
        gain = kp_lo + max(0.0, kp_hi - kp_lo) * (t ** curve)

        # Aim magnet / sticky zone: when close to the crosshair, do not slow down too much.
        sticky_radius = max(0.0, float(getattr(self.mouse_config, "sticky_radius_px", 90)))
        sticky_strength = max(1.0, float(getattr(self.mouse_config, "sticky_strength", 1.65)))
        if sticky_radius > 0 and dist <= sticky_radius:
            sticky_t = 1.0 - min(dist / sticky_radius, 1.0)
            target_size = max(1.0, min(target.width, target.height))
            small_bonus = min(0.45, max(0.0, (32.0 - target_size) / 64.0))
            gain *= 1.0 + (sticky_strength - 1.0 + small_bonus) * sticky_t

        raw_dx = error_x * gain * float(self.mouse_config.sensitivity)
        raw_dy = error_y * gain * float(self.mouse_config.sensitivity)

        # 引入 D 项（预测/阻尼/后座补偿），利用 Kalman 滤波器得到的目标在屏幕上的移动速度。
        # 它可以预测目标接下来的位置（解决跟着影子打），同时当自己准心因为后座力上跳时，
        # 目标在画面里会体现为一个向下的速度，D项会立刻向下拉枪（解决压不住准心）。
        kd = float(getattr(self.mouse_config, "kd", 0.0))
        if kd > 0.0:
            vx, vy = getattr(self._kalman, "velocity", (0.0, 0.0))
            
            # 对卡尔曼速度做平滑去噪，防止静止或者极轻微移动时由于边框微小抖动引发边缘剧烈抽搐
            v_mag = hypot(vx, vy)
            v_deadzone = 1.5
            if v_mag < v_deadzone:
                vx, vy = 0.0, 0.0
            else:
                # 软起步削减：平滑过滤抖动，越过死区后平滑过渡
                scale = (v_mag - v_deadzone) / v_mag
                vx *= scale
                vy *= scale

            # 只有当非极其微小的扰动时，才施加 D 补偿
            # d_dx, d_dy 表示我们要给出的提前/补偿量
            d_dx = vx * kd
            d_dy = vy * kd
            
            # 使用 kd_max_ratio 限制 D 项的最大输出占比，避免由于突然的画面跳变导致鼠标乱飞
            kd_max_ratio = float(getattr(self.mouse_config, "kd_max_ratio", 0.0))
            if kd_max_ratio > 0.0:
                max_d_contrib = max_step * kd_max_ratio
                d_mag = hypot(d_dx, d_dy)
                if d_mag > max_d_contrib:
                    d_dx = d_dx * (max_d_contrib / d_mag)
                    d_dy = d_dy * (max_d_contrib / d_mag)
            
            raw_dx += d_dx * float(self.mouse_config.sensitivity)
            raw_dy += d_dy * float(self.mouse_config.sensitivity)

        # Speed cap. Allow only a mild boost; avoids growing into a big swing.
        boost = max(1.0, float(self.mouse_config.max_step_boost))
        effective_max = max_step * (1.0 + min(boost - 1.0, 0.35) * t)
        magnitude = hypot(raw_dx, raw_dy)
        if magnitude > effective_max:
            scale = effective_max / magnitude
            raw_dx *= scale
            raw_dy *= scale

        # Acceleration limit, prevents suddenly increasing output after several small moves.
        sign_flip_x = self._prev_error_x != 0.0 and error_x * self._prev_error_x < 0.0
        sign_flip_y = self._prev_error_y != 0.0 and error_y * self._prev_error_y < 0.0
        if sign_flip_x:
            self._smooth_dx = 0.0
            self._residual_dx = 0.0
        if sign_flip_y:
            self._smooth_dy = 0.0
            self._residual_dy = 0.0

        max_delta = max(3.0, max_step * 0.22)
        raw_dx = self._smooth_dx + max(-max_delta, min(max_delta, raw_dx - self._smooth_dx))
        raw_dy = self._smooth_dy + max(-max_delta, min(max_delta, raw_dy - self._smooth_dy))
        self._smooth_dx = raw_dx
        self._smooth_dy = raw_dy
        self._prev_error_x = error_x
        self._prev_error_y = error_y

        if bool(getattr(self.mouse_config, "micro_accel", True)):
            raw_dx += self._residual_dx
            raw_dy += self._residual_dy
            dx = int(round(raw_dx))
            dy = int(round(raw_dy))
            self._residual_dx = max(-2.0, min(2.0, raw_dx - dx))
            self._residual_dy = max(-2.0, min(2.0, raw_dy - dy))
        else:
            dx = int(round(raw_dx))
            dy = int(round(raw_dy))

        # Minimum correction inside sticky zone, so static small targets can be pulled to center.
        min_step = max(0, int(getattr(self.mouse_config, "min_step_px", 2)))
        if min_step > 0 and dist <= max(sticky_radius, max_step * 3) and dist > deadzone:
            if dx == 0 and abs(error_x) > deadzone:
                dx = min_step if error_x > 0 else -min_step
            if dy == 0 and abs(error_y) > deadzone:
                dy = min_step if error_y > 0 else -min_step

        return AimStep(dx, dy, target)

    def _reset_state(self) -> None:
        self._smooth_dx = 0.0
        self._smooth_dy = 0.0
        self._residual_dx = 0.0
        self._residual_dy = 0.0
        self._prev_error_x = 0.0
        self._prev_error_y = 0.0
        self._in_deadzone = True

    # ------------------------------------------------------------------
    # Legacy EMA modes
    # ------------------------------------------------------------------

    def _aim_legacy(self, target: Detection | None, frame_width: int, frame_height: int, mode: str) -> AimStep:
        if target is None:
            self._smooth_dx = 0.0
            self._smooth_dy = 0.0
            return AimStep(0, 0, None)

        center_x = frame_width / 2.0
        center_y = frame_height / 2.0
        aim_x, aim_y = self._aim_point(target)
        raw_dx = (aim_x - center_x) * self.mouse_config.sensitivity
        raw_dy = (aim_y - center_y) * self.mouse_config.sensitivity

        alpha = max(0.0, min(0.98, self.mouse_config.smoothing))
        limit_scale = 1.0
        if mode == "direct":
            self._smooth_dx = raw_dx
            self._smooth_dy = raw_dy
        else:
            if mode == "eased":
                alpha = max(alpha, 0.78)
            elif mode == "stepped":
                alpha = max(alpha, 0.35)
                limit_scale = 0.45
            self._smooth_dx = self._smooth_dx * alpha + raw_dx * (1.0 - alpha)
            self._smooth_dy = self._smooth_dy * alpha + raw_dy * (1.0 - alpha)

        dx = self._clamp_step(self._smooth_dx, limit_scale)
        dy = self._clamp_step(self._smooth_dy, limit_scale)
        if abs(dx) <= self.mouse_config.deadzone_px:
            dx = 0
        if abs(dy) <= self.mouse_config.deadzone_px:
            dy = 0
        return AimStep(dx, dy, target)

    def _aim_point(self, detection: Detection) -> tuple[float, float]:
        x1, y1, x2, y2 = detection.xyxy
        
        # 解析水平瞄准点
        offset_x = float(getattr(self.target_config, "aim_offset_x", 0.0))
        if 0.0 <= offset_x <= 1.0: # 如果输入 0~1 的比例，映射为 -0.5 ~ 0.5 方便计算，0.5代表中心
            offset_x = offset_x - 0.5

        # 解析垂直瞄准点
        offset_y = float(getattr(self.target_config, "aim_offset_y", 0.0))
        if 0.0 <= offset_y <= 1.0: # 核心改动：支持输入 0~1 的比例，0 为顶边，1为底边。
            offset_y = offset_y - 0.5

        x = (x1 + x2) / 2.0 + detection.width * offset_x
        y = (y1 + y2) / 2.0 + detection.height * offset_y
        return x, y

    def _clamp_step(self, value: float, limit_scale: float = 1.0) -> int:
        limit = max(1, round(self.mouse_config.max_step_px * limit_scale))
        return int(max(-limit, min(limit, round(value))))
