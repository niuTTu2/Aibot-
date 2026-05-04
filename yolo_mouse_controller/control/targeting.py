"""
极简自瞄控制器 - 控制理论重构版 v2
基于连续非线性增益函数 + 纯 PD 控制 + 速度前馈

核心原则：
1. 无离散状态机 - 所有逻辑用连续函数表达
2. 无增益突变 - 指数平滑过渡
3. 无开环积分 - 使用短队列反馈延迟补偿
4. 纯数学驱动 - 删除所有 guard/brake/settle

v2 修复：
- Kalman 惯性预测（Target Coasting）- 解决 YOLO 漏帧断触
- Δt 归一化 - 解耦帧率，FPS 波动不影响手感
- 压枪前馈 - 开环补偿后座力
- 反馈延迟补偿 - 抵消已发送但未反映到截图里的移动
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from math import hypot

import numpy as np

from yolo_mouse_controller.config import MouseConfig, TargetConfig, TriggerPreset
from yolo_mouse_controller.vision import Detection


@dataclass(frozen=True)
class AimStep:
    dx: int
    dy: int
    target: Detection | None


class _KalmanTracker:
    """2D 恒速 Kalman 滤波器，带创新门限。

    单位约定：
    - x/y: 当前裁剪画面里的像素坐标
    - vx/vy: 像素 / 秒

    旧实现把速度近似存成“每 60FPS 基准帧的像素位移”，后面又按当前帧
    和绝对毫秒预测去用，帧率一高就容易追着旧位置/影子走。这里统一成
    px/s，所有预测和速度前馈都按真实 dt 计算。
    """

    def __init__(self, process_noise: float = 8.0, measure_noise: float = 4.0, gate_sigma: float = 4.0) -> None:
        self._x = np.zeros(4, dtype=np.float64)
        self._P = np.diag([500.0, 500.0, 20000.0, 20000.0]).astype(np.float64)
        self._F = np.array([
            [1, 0, 1.0 / 60.0, 0],
            [0, 1, 0, 1.0 / 60.0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float64)
        self._H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float64)
        self._R = np.eye(2, dtype=np.float64) * measure_noise
        self._gate_sigma = gate_sigma
        self._initialized = False
        self._miss_count = 0
        self._dt_baseline = 1.0 / 60.0
        self._process_noise = float(process_noise)

    def _set_dt(self, dt: float | None) -> float:
        dt = self._dt_baseline if dt is None or dt <= 0 else float(dt)
        dt = max(1.0 / 300.0, min(0.12, dt))
        self._F[0, 2] = dt
        self._F[1, 3] = dt
        return dt

    def _process_Q(self, dt: float) -> np.ndarray:
        # 恒速模型 + 白加速度噪声。乘 250 是为了沿用当前 UI 里 3~20
        # 这一档 process_noise 的手感范围。
        q = max(1e-6, self._process_noise) * 250.0
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt2 * dt2
        return np.array([
            [dt4 / 4 * q, 0.0,          dt3 / 2 * q, 0.0],
            [0.0,          dt4 / 4 * q, 0.0,          dt3 / 2 * q],
            [dt3 / 2 * q, 0.0,          dt2 * q,      0.0],
            [0.0,          dt3 / 2 * q, 0.0,          dt2 * q],
        ], dtype=np.float64)

    def reset(self) -> None:
        self._initialized = False
        self._miss_count = 0
        self._P = np.diag([500.0, 500.0, 20000.0, 20000.0]).astype(np.float64)

    def update(self, x: float, y: float, dt: float = None) -> tuple[float, float]:
        dt = self._set_dt(dt)

        if not self._initialized:
            self._x[:] = [x, y, 0.0, 0.0]
            self._initialized = True
            self._miss_count = 0
            return x, y

        self._miss_count = 0

        # Predict
        F = self._F.copy()
        x_pred = F @ self._x
        P_pred = F @ self._P @ F.T + self._process_Q(dt)

        # Innovation gate
        z = np.array([x, y], dtype=np.float64)
        innov = z - self._H @ x_pred
        S = self._H @ P_pred @ self._H.T + self._R
        S_inv = np.linalg.pinv(S)
        mahal_sq = float(innov @ S_inv @ innov)

        gate_sq = self._gate_sigma ** 2
        if mahal_sq > gate_sq:
            # 目标突然跳跃：重置位置，衰减速度
            self._x[0] = x
            self._x[1] = y
            self._x[2] *= 0.15
            self._x[3] *= 0.15
            self._P = np.diag([500.0, 500.0, 20000.0, 20000.0]).astype(np.float64)
            return x, y

        # Update
        K = P_pred @ self._H.T @ S_inv
        self._x = x_pred + K @ innov
        self._P = (np.eye(4, dtype=np.float64) - K @ self._H) @ P_pred
        return float(self._x[0]), float(self._x[1])

    def predict(self, dt: float = None) -> tuple[float, float]:
        if not self._initialized:
            return 0.0, 0.0
        self._miss_count += 1
        if self._miss_count > 5:
            self.reset()
            return 0.0, 0.0
        dt = self._set_dt(dt)

        self._x = self._F @ self._x
        self._P = self._F @ self._P @ self._F.T + self._process_Q(dt)
        return float(self._x[0]), float(self._x[1])

    @property
    def velocity(self) -> tuple[float, float]:
        return float(self._x[2]), float(self._x[3])


class ElegantAimController:
    """极简自瞄控制器 - 纯数学驱动 v2"""

    def __init__(self, target_config: TargetConfig, mouse_config: MouseConfig) -> None:
        self.target_config = target_config
        self.mouse_config = mouse_config
        self._active_trigger_preset: TriggerPreset | None = None

        # 仅保留必要的状态
        self._residual_dx = 0.0
        self._residual_dy = 0.0
        self._kalman = _KalmanTracker(
            process_noise=mouse_config.kalman_process_noise,
            measure_noise=mouse_config.kalman_measure_noise,
            gate_sigma=mouse_config.kalman_gate_sigma,
        )

        # v2 新增：时间戳与扳机状态
        self._last_update_time: float | None = None
        self._fire_active = False
        self._coasting_frames = 0  # 惯性预测帧数

        # 只保留这两个避震变量
        self._prev_err_x = 0.0
        self._prev_err_y = 0.0
        self._smooth_d_x = 0.0
        self._smooth_d_y = 0.0

        # 目标锁定状态
        self._locked: Detection | None = None
        self._lock_miss = 0

        # 已发出但还没反馈到截图里的鼠标移动。云电脑、采集卡、DXGI
        # 都可能有 1~4 帧反馈延迟；不抵消这部分，控制器会反复追同一个
        # 滞后画面，表现就是“跟着影子走”。
        self._pending_feedback_moves: list[tuple[float, float, int]] = []

    def set_active_trigger(self, preset: TriggerPreset | None) -> None:
        self._active_trigger_preset = preset

    def set_fire_active(self, active: bool) -> None:
        """设置扳机开火状态（用于压枪补偿）"""
        self._fire_active = bool(active)

    def record_sent_move(self, dx: int, dy: int) -> None:
        """记录已发送的移动，用于反馈延迟补偿。

        app.py 已经在鼠标移动成功后调用这个方法；之前 targeting.py 没实现，
        所以 UI/配置里的 feedback_delay_frames 实际没有生效。
        """
        delay = int(getattr(self.mouse_config, "feedback_delay_frames", 0) or 0)
        comp = float(getattr(self.mouse_config, "feedback_compensation", 0.0) or 0.0)
        if delay <= 0 or comp <= 0.0 or (dx == 0 and dy == 0):
            return
        self._pending_feedback_moves.append((float(dx), float(dy), 0))

    def _pending_feedback_offset(self) -> tuple[float, float]:
        delay = int(getattr(self.mouse_config, "feedback_delay_frames", 0) or 0)
        comp = float(getattr(self.mouse_config, "feedback_compensation", 0.0) or 0.0)
        if delay <= 0 or comp <= 0.0:
            self._pending_feedback_moves.clear()
            return 0.0, 0.0

        gx = float(getattr(self.mouse_config, "visual_gain_x", 1.0) or 1.0)
        gy = float(getattr(self.mouse_config, "visual_gain_y", 1.0) or 1.0)
        sx = sum(dx for dx, _, _ in self._pending_feedback_moves) * gx * comp
        sy = sum(dy for _, dy, _ in self._pending_feedback_moves) * gy * comp
        return sx, sy

    def _age_pending_feedback(self) -> None:
        delay = int(getattr(self.mouse_config, "feedback_delay_frames", 0) or 0)
        if delay <= 0:
            self._pending_feedback_moves.clear()
            return
        aged: list[tuple[float, float, int]] = []
        for dx, dy, age in self._pending_feedback_moves:
            new_age = age + 1
            if new_age < delay:
                aged.append((dx, dy, new_age))
        self._pending_feedback_moves = aged

    def select(self, detections: list[Detection], frame_width: int, frame_height: int) -> Detection | None:
        """
        目标选择逻辑（保留原版核心逻辑）

        优先级：
        1. 类别过滤
        2. 目标锁定（防止切换抖动）
        3. 距离/置信度排序
        """
        # 类别过滤
        allowed = set(self.target_config.class_names)
        candidates = [
            item
            for item in detections
            if not allowed or item.class_name in allowed or str(item.class_id) in allowed
        ]

        if not candidates:
            self._lock_miss += 1
            if self._lock_miss > self.mouse_config.lock_miss_frames:
                self._locked = None
            return None

        center_x = frame_width / 2.0
        center_y = frame_height / 2.0

        def dist_to_center(item: Detection) -> float:
            x, y = self._aim_point(item)
            return hypot(x - center_x, y - center_y)

        # 目标锁定逻辑
        if self.mouse_config.lock_target and self._locked is not None:
            locked_match = self._match_locked_target(candidates)
            if locked_match is not None:
                self._locked = locked_match
                self._lock_miss = 0
                target = locked_match
            else:
                self._lock_miss += 1
                if self._lock_miss > self.mouse_config.lock_miss_frames:
                    self._locked = None
                    self._lock_miss = 0
                    target = self._fresh_select(candidates, center_x, center_y, dist_to_center)
                else:
                    return None
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

    def _match_locked_target(self, candidates: list[Detection]) -> Detection | None:
        """匹配锁定目标（IoU + 距离）"""
        if self._locked is None or not candidates:
            return None

        locked = self._locked
        lx, ly = self._aim_point(locked)
        locked_size = max(1.0, max(locked.width, locked.height))
        locked_area = max(1.0, locked.width * locked.height)

        # 优先使用 IoU 匹配
        best_iou = 0.0
        best_iou_match: Detection | None = None
        for candidate in candidates:
            iou = self._bbox_iou(locked, candidate)
            if iou > best_iou:
                best_iou = iou
                best_iou_match = candidate
        if best_iou_match is not None and best_iou >= 0.10:
            return best_iou_match

        # 回退到距离匹配
        def lock_center_dist(item: Detection) -> float:
            x, y = self._aim_point(item)
            return hypot(x - lx, y - ly)

        nearest = min(candidates, key=lock_center_dist)
        nearest_dist = lock_center_dist(nearest)

        size_gate = max(36.0, min(160.0, locked_size * 3.4))
        area_ratio = (nearest.width * nearest.height) / locked_area
        same_scale = 0.35 <= area_ratio <= 2.8
        same_class = nearest.class_id == locked.class_id

        if nearest_dist <= size_gate and (same_class or same_scale):
            return nearest
        return None

    def _fresh_select(self, candidates: list[Detection], center_x: float, center_y: float, dist_fn) -> Detection | None:
        """新目标选择（距离/置信度排序）"""
        if not candidates:
            return None

        # 按距离或置信度排序
        prefer_center = bool(self.target_config.prefer_center)

        def score(det: Detection) -> tuple[float, float]:
            dist = dist_fn(det)
            if prefer_center:
                return (dist, -det.confidence)  # 距离优先
            else:
                return (-det.confidence, dist)  # 置信度优先

        return min(candidates, key=score)

    @staticmethod
    def _bbox_iou(a: Detection, b: Detection) -> float:
        """计算 IoU"""
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

    def aim(self, target: Detection | None, frame_width: int, frame_height: int, dt: float = None) -> AimStep:
        """
        极简自瞄算法 v2 - 连续非线性 PD 控制 + 工程优化

        核心公式：
        1. 误差向量：e = aim_point - center
        2. 连续增益：K_adaptive = K_min + (K_max - K_min) * (1 - exp(-dist / tau))
        3. 期望速度：V_des = K_adaptive * e
        4. 阻尼输出：u = V_des + K_d * (V_des - V_kalman)
        5. 压枪前馈：u_y += recoil_compensation (开环)

        v2 优化：
        - Kalman 惯性预测（最多 3 帧）
        - Δt 归一化（解耦帧率）
        - 压枪前馈补偿
        """
        center_x = frame_width / 2.0
        center_y = frame_height / 2.0

        # 计算 Δt（归一化到 60 FPS 基准）
        now = time.perf_counter()
        if dt is not None and dt > 0:
            dt = max(1.0 / 240.0, min(0.1, float(dt)))
        elif self._last_update_time is None:
            dt = 1.0 / 60.0  # 首帧假设 60 FPS
        else:
            dt = max(1.0 / 240.0, min(0.1, now - self._last_update_time))  # 限制在 10~240 FPS
        self._last_update_time = now

        # 归一化因子：当前帧率相对于 60 FPS 的比例
        # 例如：120 FPS 时 dt_norm = 0.5，所有增益自动减半
        dt_norm = dt / (1.0 / 60.0)
        feedback_x, feedback_y = self._pending_feedback_offset()

        # 🔥 修复1：无目标时直接返回 0 移动（禁用惯性预测）
        if target is None:
            self._coasting_frames += 1
            if self._coasting_frames > 3:
                # 连续丢失超过 3 帧，彻底重置
                self._kalman.reset()
                self._residual_dx = 0.0
                self._residual_dy = 0.0
                self._prev_err_x = 0.0  # 清空刹车记忆
                self._prev_err_y = 0.0  # 清空刹车记忆
                self._coasting_frames = 0
                self._pending_feedback_moves.clear()
            self._age_pending_feedback()
            return AimStep(0, 0, None)

        # 有目标，重置惯性计数
        self._coasting_frames = 0
        # 1. Kalman 滤波获取平滑位置与速度
        raw_x, raw_y = self._aim_point(target)
        aim_x, aim_y = self._kalman.update(raw_x, raw_y, dt)
        vx, vy = self._kalman.velocity

        # 🔥 终极形态核心 1：绝对时间预测 (Predictive Lead)
        # 不要追现在的影子，直接去未来等他！
        # 假设你的系统总延迟是 15ms (0.015秒)，你可以在 config 里通过 prediction_ms 调整
        latency_sec = float(getattr(self.mouse_config, "prediction_ms", 15.0)) / 1000.0
        future_x = aim_x + vx * latency_sec
        future_y = aim_y + vy * latency_sec

        # 2. 计算【未来误差】
        # feedback_x/y 是最近已发出的鼠标位移预计会在后续截图里造成的
        # 视觉位移，先从当前误差里抵消，避免重复追逐滞后画面。
        err_x = future_x - center_x - feedback_x
        err_y = future_y - center_y - feedback_y
        dist = hypot(err_x, err_y)

        # 3. 动态量化死区 (唯一保留的避震器)
        target_size = max(target.width, target.height)
        dynamic_deadzone = max(2.5, min(6.0, target_size * 0.03))

        if dist <= dynamic_deadzone:
            # 只要贴近了未来的目标，切断所有牵引力
            self._residual_dx = 0.0
            self._residual_dy = 0.0
            self._age_pending_feedback()
            return AimStep(0, 0, target)

        # 4. 极其温柔的 P 牵引力 (Tether Correction)
        # 因为前馈承担了 90% 的工作，这里的 P 可以设得很小，仅仅用来纠正微弱的偏移
        tau = max(1.0, float(self.mouse_config.sticky_radius_px))
        smooth_factor = 1.0 - math.exp(-dist / tau)
        
        kp_adaptive = (float(self.mouse_config.kp_min) +
                      (float(self.mouse_config.kp) - float(self.mouse_config.kp_min)) * smooth_factor) * dt_norm

        tether_x = err_x * kp_adaptive
        tether_y = err_y * kp_adaptive

        # 🔥 终极形态核心 2：纯粹的速度匹配前馈 (Velocity Feedforward)
        # 敌人的速度 vx, vy 就是鼠标底盘的基础动力！
        kv = float(self.mouse_config.kd)  # 借用 kd 参数作为前馈系数，通常设为 0.8 到 1.0
        
        ff_x = vx * dt * kv
        ff_y = vy * dt * kv
        kd_max_ratio = float(getattr(self.mouse_config, "kd_max_ratio", 0.0) or 0.0)
        if kd_max_ratio > 0.0:
            ff_cap = max(1.0, float(self.mouse_config.max_step_px) * kd_max_ratio)
            ff_x = max(-ff_cap, min(ff_cap, ff_x))
            ff_y = max(-ff_cap, min(ff_cap, ff_y))

        # 5. 最终输出 = 同步伴飞(前馈) + 未来牵引(P修正)
        # 没有积分，没有微分，干干净净，绝不震荡！
        out_x = ff_x + tether_x
        out_y = ff_y + tether_y

        # 6. 开环压枪补偿
        if self._fire_active and self._active_trigger_preset is not None:
            recoil_pull_y = float(getattr(self._active_trigger_preset, "recoil_pull_y", 0.0))
            if recoil_pull_y > 0 and err_y > 0:
                magnetic_zone = 25.0
                pull_ratio = min(err_y / magnetic_zone, 1.0)
                # 依然使用加法弹性补偿，确保压枪力量不受死区影响
                out_y += (recoil_pull_y * dt_norm) * pull_ratio

        # 6. 应用全局灵敏度 + 小数累积（Micro Accel）
        sensitivity = float(self.mouse_config.sensitivity)
        out_x = out_x * sensitivity + self._residual_dx
        out_y = out_y * sensitivity + self._residual_dy

        dx = int(round(out_x))
        dy = int(round(out_y))
        self._residual_dx = out_x - dx
        self._residual_dy = out_y - dy

        # 7. 全局最大步长硬限幅
        max_step = int(self.mouse_config.max_step_px)
        dx = max(-max_step, min(max_step, dx))
        dy = max(-max_step, min(max_step, dy))

        self._age_pending_feedback()
        return AimStep(dx, dy, target)

    def _aim_point(self, detection: Detection) -> tuple[float, float]:
        """计算瞄准点（支持 X/Y 偏移）"""
        x1, y1, x2, y2 = detection.xyxy

        # 解析水平瞄准点
        offset_x = float(getattr(self.target_config, "aim_offset_x", 0.0))
        if 0.0 <= offset_x <= 1.0:
            offset_x = offset_x - 0.5

        # 解析垂直瞄准点（支持扳机预设覆盖）
        trigger_preset = self._active_trigger_preset
        trigger_offset_y = getattr(trigger_preset, "aim_offset_y", None) if trigger_preset is not None else None
        offset_y = float(trigger_offset_y if trigger_offset_y is not None else getattr(self.target_config, "aim_offset_y", 0.0))
        if 0.0 <= offset_y <= 1.0:
            offset_y = offset_y - 0.5

        x = (x1 + x2) / 2.0 + detection.width * offset_x
        y = (y1 + y2) / 2.0 + detection.height * offset_y
        return x, y

    def target_distance(self, target: Detection, frame_width: int, frame_height: int) -> float:
        """计算目标到准星的距离（用于扳机条件判断）"""
        center_x = frame_width / 2.0
        center_y = frame_height / 2.0
        aim_x, aim_y = self._aim_point(target)
        return hypot(aim_x - center_x, aim_y - center_y)
