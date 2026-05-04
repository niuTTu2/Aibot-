from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yolo_mouse_controller.control.hotkeys import Hotkeys
    from yolo_mouse_controller.control.mouse import MouseController

from yolo_mouse_controller.config import TriggerPreset


class TriggerController:
    """
    鐙珛绾跨▼鎵虫満鐘舵€佹満銆?
    涓诲惊鐜瘡甯ц皟鐢?update(target_dist, hotkeys)锛岄潪闃诲銆?
    鍐呴儴绾跨▼澶勭悊 burst/bolt 鐨?sleep锛屼笉闃诲涓诲惊鐜€?
    """

    def __init__(self, preset: TriggerPreset, mouse: MouseController) -> None:
        self.preset = preset
        self.mouse = mouse

        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # 涓诲惊鐜啓锛屽伐浣滅嚎绋嬭
        self._armed = False
        self._in_range = False
        self._manual_left_down = False
        self._trigger_event = threading.Event()

        # 宸ヤ綔绾跨▼鐙崰鍐?
        self._state = "idle"  # idle | firing | cooldown
        self._pressed = False
        self._last_trigger_press_at = 0.0

        self._worker = threading.Thread(target=self._run, daemon=True, name=f"trigger-{preset.name}")
        self._worker.start()

    def update(self, target_dist: float | None, hotkeys: Hotkeys | None = None, armed: bool | None = None) -> None:
        # armed 鏈樉寮忎紶鍏ユ椂锛屽吋瀹规棫閫昏緫锛氭寜 trigger_keys 鍒ゅ畾
        if armed is None:
            armed = bool(hotkeys and any(hotkeys.is_down(k) for k in self.preset.trigger_keys))

        # 鎵嬪姩宸﹂敭濮嬬粓浼樺厛銆?
        # 鐜╁鑷繁宸茬粡鍦ㄥ紑鐏椂锛屾壋鏈轰笉寰楀啀鎻掑叆 click/press/release锛?
        # 鍚﹀垯浼氭姠鍗犲乏閿富鏉冿紝閫犳垚鈥滀腑閫旀柇鏋€濄€?
        physical_left_down = hotkeys.is_physical_left_down() if hotkeys and hasattr(hotkeys, "is_physical_left_down") else None
        physical_down_at = hotkeys.physical_left_down_at() if hotkeys and hasattr(hotkeys, "physical_left_down_at") else None
        manual_left_down = False
        if physical_left_down is not None:
            manual_left_down = bool(physical_left_down)
            # If a driver backend echoes our own press as a physical event, do
            # not treat it as player takeover unless a new physical down event
            # happened after our synthetic/driver press.
            if self._pressed and physical_down_at is not None and physical_down_at <= self._last_trigger_press_at + 0.10:
                manual_left_down = False
        else:
            manual_left_down = bool(hotkeys and hotkeys.is_down(0x01) and not self._pressed)

        if manual_left_down:
            if self._pressed:
                # Trigger was holding left, then the player also physically pressed left.
                # Transfer ownership to the player's real button WITHOUT sending release;
                # otherwise target loss would cancel manual fire.
                self._pressed = False
            armed = False

        # distance mode: target_dist is actual distance and must be <= fire_distance_px.
        # area mode: caller passes 0.0 when the target box intersects the configured
        # fire area, otherwise None. Keeping the comparison here preserves backward
        # compatibility with older call sites/configs.
        in_range = target_dist is not None and target_dist <= self.preset.fire_distance_px
        with self._lock:
            prev_armed = self._armed
            prev_in_range = self._in_range
            self._armed = armed
            self._in_range = in_range
            self._manual_left_down = manual_left_down

        rising = (armed and in_range) and not (prev_armed and prev_in_range)
        if rising:
            self._trigger_event.set()

        if not (armed and in_range):
            self._trigger_event.set()

    @property
    def is_pressed(self) -> bool:
        return bool(self._pressed)

    def close(self) -> None:
        self._stop_event.set()
        self._trigger_event.set()
        self._worker.join(timeout=1.0)
        if self._pressed:
            try:
                self.mouse.left_release()
            except Exception:
                pass

    def _run(self) -> None:
        mode = self.preset.mode
        while not self._stop_event.is_set():
            self._trigger_event.wait(timeout=0.05)
            self._trigger_event.clear()

            if self._stop_event.is_set():
                break

            with self._lock:
                armed = self._armed
                in_range = self._in_range

            should_fire = armed and in_range

            if mode == "hold":
                self._run_hold(should_fire)
            elif mode == "burst":
                if should_fire and self._state == "idle":
                    self._run_burst()
            elif mode == "semi":
                if should_fire and self._state == "idle":
                    self._run_semi()
                elif not should_fire:
                    self._state = "idle"
            elif mode == "bolt":
                if should_fire and self._state == "idle":
                    self._run_bolt()

        self._release()

    def _should_continue(self) -> bool:
        with self._lock:
            if self._manual_left_down and not self._pressed:
                return False
            return self._armed and self._in_range and not self._stop_event.is_set()

    def _press(self) -> None:
        if not self._pressed:
            self._last_trigger_press_at = time.perf_counter()
            self.mouse.left_press()
            self._pressed = True

    def _release(self) -> None:
        if self._pressed:
            with self._lock:
                manual_left_down = self._manual_left_down
            if manual_left_down:
                # Player is physically holding fire. Do not send synthetic
                # release; just drop trigger ownership so the real button
                # remains authoritative.
                self._pressed = False
                return
            self.mouse.left_release()
            self._pressed = False

    def _click(self) -> None:
        self.mouse.left_click()

    def _wait_until_settled(self) -> bool:
        delay_ms = max(0, int(getattr(self.preset, "settle_delay_ms", 0)))
        if delay_ms <= 0:
            return self._should_continue()

        end = time.perf_counter() + delay_ms / 1000.0
        while time.perf_counter() < end:
            if not self._should_continue():
                return False
            time.sleep(0.001)
        return self._should_continue()

    def _run_hold(self, should_fire: bool) -> None:
        if not should_fire:
            self._release()
            self._state = "idle"
            return

        duration = self.preset.fire_duration_ms
        if duration <= 0:
            if not self._wait_until_settled():
                self._state = "idle"
                return
            self._press()
            self._state = "firing"
            return

        self._state = "firing"
        while self._should_continue():
            if not self._wait_until_settled():
                break
            self._press()
            end = time.perf_counter() + duration / 1000.0
            while time.perf_counter() < end:
                if not self._should_continue():
                    break
                time.sleep(0.001)
            self._release()
            if not self._should_continue():
                break
            time.sleep(0.01)
        self._state = "idle"

    def _run_burst(self) -> None:
        self._state = "firing"
        if not self._wait_until_settled():
            self._state = "idle"
            return
        count = max(1, self.preset.burst_count)
        interval = max(10, self.preset.burst_interval_ms) / 1000.0
        for i in range(count):
            if not self._should_continue():
                break
            self._click()
            if i < count - 1:
                time.sleep(interval)
        self._state = "idle"

    def _run_semi(self) -> None:
        self._state = "firing"
        if not self._wait_until_settled():
            self._state = "idle"
            return
        self._click()
        while self._should_continue():
            time.sleep(0.01)
        self._state = "idle"

    def _run_bolt(self) -> None:
        self._state = "firing"
        if not self._wait_until_settled():
            self._state = "idle"
            return
        self._click()
        self._state = "cooldown"
        delay = self.preset.bolt_delay_ms / 1000.0
        end = time.perf_counter() + delay
        while time.perf_counter() < end and not self._stop_event.is_set():
            time.sleep(0.01)
        self._state = "idle"

