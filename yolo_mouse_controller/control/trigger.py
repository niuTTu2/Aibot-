from __future__ import annotations

import time

from yolo_mouse_controller.config import TriggerPreset
from yolo_mouse_controller.control.hotkeys import Hotkeys
from yolo_mouse_controller.control.mouse import MouseController


class TriggerController:
    def __init__(self, preset: TriggerPreset, mouse: MouseController) -> None:
        self.preset = preset
        self.mouse = mouse
        self._holding = False
        self._last_shot_at = 0.0
        self._hold_deadline = 0.0
        self._was_in_range = False

    def close(self) -> None:
        if self._holding:
            self.mouse.left_release()
            self._holding = False

    def update(self, target_dist: float | None, hotkeys: Hotkeys, armed: bool = True) -> None:
        now = time.perf_counter()
        in_range = self._is_in_range(target_dist)
        enabled = armed and self._hotkey_active(hotkeys)

        if self._holding and self._hold_deadline > 0.0 and now >= self._hold_deadline:
            self.mouse.left_release()
            self._holding = False
            self._hold_deadline = 0.0

        if not enabled:
            self._was_in_range = in_range
            if self._holding:
                self.mouse.left_release()
                self._holding = False
                self._hold_deadline = 0.0
            return

        mode = (self.preset.mode or "hold").lower()
        if mode == "hold":
            self._update_hold(in_range, now)
        elif mode == "burst":
            self._update_burst(in_range, now)
        elif mode == "semi":
            self._update_semi(in_range, now)
        elif mode == "bolt":
            self._update_bolt(in_range, now)
        else:
            self._update_hold(in_range, now)

        self._was_in_range = in_range

    def _is_in_range(self, target_dist: float | None) -> bool:
        if target_dist is None:
            return False
        return target_dist <= float(self.preset.fire_distance_px)

    def _hotkey_active(self, hotkeys: Hotkeys) -> bool:
        keys = list(self.preset.trigger_keys or [])
        if not keys:
            return True
        return any(hotkeys.is_down(int(k)) for k in keys)

    def _update_hold(self, in_range: bool, now: float) -> None:
        duration = max(0, int(self.preset.fire_duration_ms)) / 1000.0
        if not in_range:
            if self._holding:
                self.mouse.left_release()
                self._holding = False
                self._hold_deadline = 0.0
            return

        if duration <= 0.0:
            if not self._holding and self.mouse.left_press():
                self._holding = True
            return

        if not self._holding:
            if self.mouse.left_press():
                self._holding = True
                self._hold_deadline = now + duration
        elif now >= self._hold_deadline:
            self.mouse.left_release()
            self._holding = False
            self._hold_deadline = 0.0

    def _update_burst(self, in_range: bool, now: float) -> None:
        if not in_range:
            return
        interval = max(1, int(self.preset.burst_interval_ms)) / 1000.0
        if now - self._last_shot_at < interval:
            return
        count = max(1, int(self.preset.burst_count))
        for _ in range(count):
            self.mouse.left_click()
        self._last_shot_at = now

    def _update_semi(self, in_range: bool, now: float) -> None:
        if in_range and not self._was_in_range:
            interval = max(1, int(self.preset.burst_interval_ms)) / 1000.0
            if now - self._last_shot_at >= interval:
                self.mouse.left_click()
                self._last_shot_at = now

    def _update_bolt(self, in_range: bool, now: float) -> None:
        if not in_range:
            return
        delay = max(1, int(self.preset.bolt_delay_ms)) / 1000.0
        if now - self._last_shot_at < delay:
            return
        self.mouse.left_click()
        self._last_shot_at = now
