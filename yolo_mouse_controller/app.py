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

from yolo_mouse_controller.control import Hotkeys, MouseController, TargetSelector, TriggerController
from yolo_mouse_controller.vision import Detection, YoloDetector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YOLO mouse controller")
    parser.add_argument("--config", default="config.example.yaml", help="Path to YAML config.")
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
    selector = TargetSelector(config.target, config.mouse)
    mouse = MouseController(config.mouse)
    hotkeys = Hotkeys()
    triggers = [TriggerController(p, mouse) for p in config.mouse.triggers] if config.mouse.trigger_enabled else []

    # 武器切换热键状态
    _switch_keys = [(i, p.switch_key) for i, p in enumerate(config.mouse.triggers) if p.switch_key] if config.mouse.trigger_enabled else []
    _active_trigger_idx: list[int] = [0]  # 用 list 封装以便内层修改
    _switch_prev: dict[int, bool] = {sk: False for _, sk in _switch_keys}

    def _check_weapon_switch() -> None:
        for idx, sk in _switch_keys:
            down = hotkeys.is_down(sk)
            if down and not _switch_prev.get(sk, False):
                # 上升沿：切换到该预设
                old = _active_trigger_idx[0]
                _active_trigger_idx[0] = idx
                preset = config.mouse.triggers[idx]
                aprint(f"WEAPON_SWITCH idx={idx} name={preset.name} key=0x{sk:02x}")
            _switch_prev[sk] = down
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

    source.start()
    aprint(
        "MOUSE_STATUS "
        "state=ready "
        f"enabled={bool_text(config.mouse.enabled)} "
        f"hold_to_move={bool_text(config.mouse.hold_to_move)} "
        f"backend={config.mouse.backend} "
        f"backend_ready={bool_text(mouse.available)} "
        f"backend_error={mouse.last_error.replace(' ', '_') or 'none'} "
        f"mode={config.mouse.movement_mode} "
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
            target = selector.select(detections, width, height)
            step = selector.aim_step(target, width, height)

            hotkey_down = True
            should_move = config.mouse.enabled
            if config.mouse.hold_to_move:
                hotkey_down = any(hotkeys.is_down(k) for k in config.mouse.enable_keys)
                should_move = should_move and hotkey_down

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

            now = time.perf_counter()
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
                cx, cy = width / 2.0, height / 2.0
                if target is not None:
                    x1, y1, x2, y2 = target.xyxy
                    tx = (x1 + x2) / 2.0
                    ty = (y1 + y2) / 2.0
                    target_dist: float | None = hypot(tx - cx, ty - cy)
                else:
                    target_dist = None
                if triggers:
                    _check_weapon_switch()
                    # 如果配置了切换热键，只更新当前激活的扳机；否则更新全部
                    trigger_armed = (not config.mouse.hold_to_move) or hotkey_down
                    if _switch_keys:
                        triggers[_active_trigger_idx[0]].update(target_dist, hotkeys, armed=trigger_armed)
                    else:
                        for trig in triggers:
                            trig.update(target_dist, hotkeys, armed=trigger_armed)

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
