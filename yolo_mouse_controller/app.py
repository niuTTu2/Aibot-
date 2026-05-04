from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path

import cv2

from yolo_mouse_controller.capture import center_crop_frame, create_frame_source, effective_crop_size
from yolo_mouse_controller.config import AppConfig, load_config
from math import hypot

from yolo_mouse_controller.control import Hotkeys, MouseController, ElegantAimController, TriggerController
from yolo_mouse_controller.vision import Detection, YoloDetector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YOLO mouse controller")
    parser.add_argument("--config", default="configs/config.example.yaml", help="Path to YAML config.")
    parser.add_argument("--source", choices=["dxgi", "capture_card"], help="Override capture source.")
    parser.add_argument("--preview", action="store_true", help="Show preview window.")
    parser.add_argument("--no-mouse", action="store_true", help="Disable mouse movement.")
    return parser.parse_args()


def apply_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    if args.source:
        config.capture.source = args.source
    if args.preview:
        config.runtime.preview = True
    if args.no_mouse:
        config.mouse.enabled = False
    return config


def draw_preview(frame, detections: list[Detection], target: Detection | None) -> None:
    for detection in detections:
        x1, y1, x2, y2 = [int(v) for v in detection.xyxy]
        is_target = detection == target
        color = (0, 220, 0) if is_target else (80, 160, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{detection.class_name} {detection.confidence:.2f}"
        cv2.putText(frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    height, width = frame.shape[:2]
    cv2.drawMarker(frame, (width // 2, height // 2), (255, 255, 255), cv2.MARKER_CROSS, 18, 1)


def prepare_preview_frame(frame, scale: float):
    scale = max(0.05, min(4.0, scale))
    if abs(scale - 1.0) < 0.001:
        return frame
    height, width = frame.shape[:2]
    preview_width = max(1, int(width * scale))
    preview_height = max(1, int(height * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    return cv2.resize(frame, (preview_width, preview_height), interpolation=interpolation)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def mouse_target_text(target: Detection | None) -> str:
    if target is None:
        return "none"
    class_name = target.class_name.replace(" ", "_")
    return f"{class_name}:{target.confidence:.2f}"


def trigger_metric(
    target: Detection | None,
    detections: list[Detection],
    selector: ElegantAimController,
    config: AppConfig,
    preset,
    frame_width: int,
    frame_height: int,
) -> float | None:
    condition = str(getattr(preset, "trigger_condition", "distance") or "distance").lower()
    if condition != "area":
        if target is None:
            return None
        return selector.target_distance(target, frame_width, frame_height)

    area_w = max(1.0, float(getattr(preset, "fire_area_width_px", 80) or 80))
    area_h = max(1.0, float(getattr(preset, "fire_area_height_px", 80) or 80))
    cx = frame_width / 2.0
    cy = frame_height / 2.0
    rx1 = cx - area_w / 2.0
    ry1 = cy - area_h / 2.0
    rx2 = cx + area_w / 2.0
    ry2 = cy + area_h / 2.0
    allowed = set(config.target.class_names)
    for item in detections:
        if allowed and item.class_name not in allowed and str(item.class_id) not in allowed:
            continue
        x1, y1, x2, y2 = item.xyxy
        intersects = max(x1, rx1) <= min(x2, rx2) and max(y1, ry1) <= min(y2, ry2)
        if intersects:
            return 0.0
    return None


class PreviewWindow:
    def __init__(self, title: str, initial_width: int, initial_height: int) -> None:
        self.title = title
        self.initial_width = max(1, initial_width)
        self.initial_height = max(1, initial_height)
        self.created = False

    def show(self, frame) -> int:
        if not self.created:
            cv2.namedWindow(self.title, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.title, self.initial_width, self.initial_height)
            self.created = True
        cv2.imshow(self.title, frame)
        # pollKey is non-blocking (no sleep), avoids the 15ms Windows timer penalty of waitKey(1)
        key = cv2.pollKey()
        return 0xFF if key == -1 else key & 0xFF


def _create_detector(model_config):
    from pathlib import Path
    suffix = Path(model_config.path).suffix.lower()
    if suffix in (".engine", ".trt", ".plan", ".rtr"):
        from yolo_mouse_controller.vision import TrtDetector
        return TrtDetector(model_config)
    return YoloDetector(model_config)


def run(config: AppConfig) -> None:
    source = create_frame_source(config.capture)
    detector = _create_detector(config.model)
    selector = ElegantAimController(config.target, config.mouse)
    mouse = MouseController(config.mouse)
    hotkeys = Hotkeys()
    triggers = [TriggerController(p, mouse) for p in config.mouse.triggers] if config.mouse.trigger_enabled else []

    # ????????
    _switch_bindings: dict[int, list[int]] = {}
    for idx, preset in enumerate(config.mouse.triggers):
        sk = int(getattr(preset, "switch_key", 0) or 0)
        if sk:
            _switch_bindings.setdefault(sk, []).append(idx)
    _switch_keys = sorted(_switch_bindings.items(), key=lambda item: item[0])
    _active_trigger_idx: list[int] = [0]
    _switch_prev: dict[int, bool] = {sk: False for sk, _ in _switch_keys}
    _last_profile_signature: list[tuple[str | None, float | None] | None] = [None]
    _weapon_switch_mode = str(getattr(config.mouse, "weapon_switch_mode", "hotkey") or "hotkey").lower()
    _weapon_next_keys = [int(k) for k in getattr(config.mouse, "weapon_next_keys", []) or []]
    _weapon_prev_keys = [int(k) for k in getattr(config.mouse, "weapon_prev_keys", []) or []]

    def _set_active_profile(idx: int, source_name: str, detail: str = "") -> None:
        if not config.mouse.triggers:
            return
        idx = max(0, min(idx, len(config.mouse.triggers) - 1))
        if idx == _active_trigger_idx[0]:
            return
        _active_trigger_idx[0] = idx
        preset = config.mouse.triggers[idx]
        aprint(
            f"WEAPON_SWITCH source={source_name} idx={idx} name={preset.name} "
            f"aim_offset_y={getattr(preset, 'aim_offset_y', None)} {detail}".strip()
        )

    def _check_weapon_switch() -> None:
        for sk, indices in _switch_keys:
            # Use a latched key edge instead of current-state polling.
            # This avoids missing short 1/2/3/4 weapon-switch taps while the
            # game is focused and the inference loop is busy.
            if hotkeys.was_pressed(sk):
                idx = indices[-1]
                _set_active_profile(idx, "hotkey", f"key=0x{sk:02x}")

    def _check_weapon_cycle() -> None:
        if not config.mouse.triggers:
            return
        for key in _weapon_next_keys:
            if hotkeys.was_pressed(key):
                _set_active_profile((_active_trigger_idx[0] + 1) % len(config.mouse.triggers), "cycle_next", f"key=0x{key:02x}")
                return
        for key in _weapon_prev_keys:
            if hotkeys.was_pressed(key):
                _set_active_profile((_active_trigger_idx[0] - 1) % len(config.mouse.triggers), "cycle_prev", f"key=0x{key:02x}")
                return

    def _active_trigger_preset():
        if not config.mouse.triggers:
            return None
        if _switch_keys:
            idx = max(0, min(_active_trigger_idx[0], len(config.mouse.triggers) - 1))
            return config.mouse.triggers[idx]
        return config.mouse.triggers[0]

    frame_count = 0
    fps_started = time.perf_counter()
    preview_scale = config.runtime.preview_scale
    preview_width, preview_height = effective_crop_size(
        config.capture.width,
        config.capture.height,
        config.capture.crop_width,
        config.capture.crop_height,
    )
    preview_window = PreviewWindow(
        "YOLO Mouse Controller",
        config.runtime.preview_initial_width or preview_width,
        config.runtime.preview_initial_height or preview_height,
    )
    last_mouse_status_at = 0.0
    last_mouse_state = ""
    last_mouse_cmd_at = 0.0

    # Async print queue — keeps flush() off the hot path
    _print_q: queue.SimpleQueue[str] = queue.SimpleQueue()

    def _print_worker() -> None:
        while True:
            msg = _print_q.get()
            if msg is None:
                break
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    _print_thread = threading.Thread(target=_print_worker, daemon=True)
    _print_thread.start()

    def aprint(msg: str) -> None:
        _print_q.put(msg)

    # v2 IPC: 跨端 UDP 加速
    import socket
    _ipc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _ipc_target = ("127.0.0.1", 8766)

    def send_ipc(msg: str) -> None:
        try:
            _ipc_sock.sendto(msg.encode("utf-8"), _ipc_target)
        except:
            pass

    duplicate_switches = {sk: ids for sk, ids in _switch_keys if len(ids) > 1}

    source.start()
    if duplicate_switches:
        for sk, ids in duplicate_switches.items():
            names = ",".join(config.mouse.triggers[i].name for i in ids)
            aprint(f"CONFIG_WARN duplicate_switch_key=0x{sk:02x} presets={names}")

    aprint(
        "MOUSE_STATUS "
        "state=ready "
        f"enabled={bool_text(config.mouse.enabled)} "
        f"hold_to_move={bool_text(config.mouse.hold_to_move)} "
        f"backend={config.mouse.backend} "
        f"backend_ready={bool_text(mouse.available)} "
        f"backend_error={mouse.last_error.replace(' ', '_') or 'none'} "
        f"mode={config.mouse.movement_mode} "
        f"visual_gain_x={getattr(config.mouse, 'visual_gain_x', 0.47):.4f} "
        f"visual_gain_y={getattr(config.mouse, 'visual_gain_y', 0.49):.4f} "
        f"feedback_delay_frames={getattr(config.mouse, 'feedback_delay_frames', 0)} "
        f"feedback_compensation={getattr(config.mouse, 'feedback_compensation', 0.0):.2f} "
        f"enable_keys={','.join(f'0x{k:02x}' for k in config.mouse.enable_keys)} "
        f"trigger_enabled={bool_text(config.mouse.trigger_enabled)} "
        f"triggers={len(config.mouse.triggers)}"
    )
    try:
        while True:
            loop_started = time.perf_counter()
            capture_started = time.perf_counter()
            frame = source.read()
            capture_ms = (time.perf_counter() - capture_started) * 1000.0
            if frame is None:
                time.sleep(0.001)
                continue
            frame = center_crop_frame(frame, config.capture.crop_width, config.capture.crop_height)

            inference_started = time.perf_counter()
            detections = detector.detect(frame)
            inference_ms = (time.perf_counter() - inference_started) * 1000.0
            height, width = frame.shape[:2]
            now = time.perf_counter()
            if _weapon_switch_mode in {"hotkey", "mixed", "all"} and _switch_keys:
                _check_weapon_switch()
            if _weapon_switch_mode in {"cycle", "mixed", "all"}:
                _check_weapon_cycle()
            active_preset = _active_trigger_preset()
            selector.set_active_trigger(active_preset)

            hotkey_down = True
            should_move = config.mouse.enabled
            if config.mouse.hold_to_move:
                hotkey_down = any(hotkeys.is_down(k) for k in config.mouse.enable_keys)
                should_move = should_move and hotkey_down

            physical_left = hotkeys.is_physical_left_down() if hasattr(hotkeys, "is_physical_left_down") else None
            manual_fire_active = bool(physical_left) if physical_left is not None else hotkeys.is_down(0x01)
            trigger_fire_active = any(bool(getattr(trig, "is_pressed", False)) for trig in triggers)
            if hasattr(selector, "set_fire_active"):
                selector.set_fire_active(manual_fire_active or trigger_fire_active)

            profile_signature = None if active_preset is None else (getattr(active_preset, "name", None), getattr(active_preset, "aim_offset_y", None))
            if profile_signature != _last_profile_signature[0]:
                if active_preset is not None:
                    aprint(
                        "AIM_PROFILE "
                        f"name={active_preset.name} "
                        f"aim_offset_y={getattr(active_preset, 'aim_offset_y', None)} "
                        f"switch_key=0x{int(getattr(active_preset, 'switch_key', 0) or 0):02x}"
                    )
                _last_profile_signature[0] = profile_signature
            target = selector.select(detections, width, height)
            step = selector.aim(target, width, height)

            if not config.mouse.enabled:
                mouse_state = "disabled"
            elif not mouse.available:
                mouse_state = "backend_unavailable"
            elif config.mouse.hold_to_move and not hotkey_down:
                mouse_state = "waiting_hotkey"
            elif target is None:
                mouse_state = "armed_no_target"
            elif step.dx == 0 and step.dy == 0:
                mouse_state = "deadzone"
            else:
                mouse_state = "moving"

            if mouse_state != last_mouse_state or now - last_mouse_status_at >= 0.5:
                aprint(
                    "MOUSE_STATUS "
                    f"state={mouse_state} "
                    f"enabled={bool_text(config.mouse.enabled)} "
                    f"hold_to_move={bool_text(config.mouse.hold_to_move)} "
                    f"hotkey_down={bool_text(hotkey_down)} "
                    f"backend={config.mouse.backend} "
                    f"backend_ready={bool_text(mouse.available)} "
                    f"backend_error={mouse.last_error.replace(' ', '_') or 'none'} "
                    f"mode={config.mouse.movement_mode} "
                    f"visual_gain_x={getattr(config.mouse, 'visual_gain_x', 0.47):.4f} "
                    f"visual_gain_y={getattr(config.mouse, 'visual_gain_y', 0.49):.4f} "
                    f"feedback_delay_frames={getattr(config.mouse, 'feedback_delay_frames', 0)} "
                    f"feedback_compensation={getattr(config.mouse, 'feedback_compensation', 0.0):.2f} "
                    f"target={mouse_target_text(target)} "
                    f"step_dx={step.dx} "
                    f"step_dy={step.dy}"
                )
                last_mouse_state = mouse_state
                last_mouse_status_at = now

            if not should_move or target is None or (step.dx == 0 and step.dy == 0):
                if hasattr(mouse, "clear_pending_move"):
                    mouse.clear_pending_move()

            if should_move:
                if step.dx != 0 or step.dy != 0:
                    moved = mouse.move_relative(step.dx, step.dy)
                    if moved:
                        if hasattr(selector, "record_sent_move"):
                            selector.record_sent_move(step.dx, step.dy)
                        # ??????????????????????????
                        if now - last_mouse_cmd_at >= 0.08:
                            aprint(
                                "MOUSE_CMD "
                                f"type=move "
                                f"backend={config.mouse.backend} "
                                f"dx={step.dx} "
                                f"dy={step.dy} "
                                f"mode={config.mouse.movement_mode} "
                                f"target={mouse_target_text(target)}"
                            )
                            last_mouse_cmd_at = now

            # 扳机：计算目标距中心距离，通知各扳机控制器
            if triggers:
                if triggers:
                    # 如果配置了切换热键，只更新当前激活的扳机；否则更新全部
                    trigger_armed = (not config.mouse.hold_to_move) or hotkey_down
                    if _switch_keys:
                        idx = _active_trigger_idx[0]
                        active_trigger_metric = trigger_metric(target, detections, selector, config, config.mouse.triggers[idx], width, height)
                        triggers[idx].update(active_trigger_metric, hotkeys, armed=trigger_armed)
                    else:
                        for idx, trig in enumerate(triggers):
                            active_trigger_metric = trigger_metric(target, detections, selector, config, config.mouse.triggers[idx], width, height)
                            trig.update(active_trigger_metric, hotkeys, armed=trigger_armed)

            if config.runtime.preview:
                draw_preview(frame, detections, step.target)
                preview_frame = prepare_preview_frame(frame, preview_scale)
                key = preview_window.show(preview_frame)
                if key != 0xFF:
                    if key == ord(config.runtime.quit_key):
                        break
                    if key in {ord("+"), ord("=")}:
                        preview_scale = min(4.0, preview_scale + 0.1)
                        aprint(f"Preview scale: {preview_scale:.2f}")
                    elif key in {ord("-"), ord("_")}:
                        preview_scale = max(0.1, preview_scale - 0.1)
                        aprint(f"Preview scale: {preview_scale:.2f}")
                    elif key == ord("0"):
                        preview_scale = 1.0
                        aprint("Preview scale: 1.00")

            frame_count += 1
            total_ms = (time.perf_counter() - loop_started) * 1000.0
            if config.runtime.print_fps and frame_count % 15 == 0:
                elapsed = time.perf_counter() - fps_started
                fps = frame_count / max(elapsed, 0.001)
                
                # 发送跨端 IPC Metrics 到 UDP
                send_ipc(
                    f"METRICS capture_ms={capture_ms:.2f} "
                    f"inference_ms={inference_ms:.2f} "
                    f"total_ms={total_ms:.2f} "
                    f"fps={fps:.1f}"
                )
                
                # 保留本地日志（也可以选择移除）
                aprint(
                    "METRICS "
                    f"capture_ms={capture_ms:.2f} "
                    f"inference_ms={inference_ms:.2f} "
                    f"total_ms={total_ms:.2f} "
                    f"fps={fps:.1f} "
                    f"detections={len(detections)} "
                    f"target={int(bool(target))}"
                )
    finally:
        _print_q.put(None)
        for trig in triggers:
            trig.close()
        mouse.close()
        source.stop()
        cv2.destroyAllWindows()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = apply_overrides(load_config(config_path), args)
    run(config)

