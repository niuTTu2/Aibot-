from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from yolo_mouse_controller.capture import center_crop_frame, create_frame_source, effective_crop_size
from yolo_mouse_controller.config import AppConfig, load_config
from yolo_mouse_controller.control import Hotkeys, MouseController, TargetSelector
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
        return cv2.waitKey(1) & 0xFF


def run(config: AppConfig) -> None:
    source = create_frame_source(config.capture)
    detector = YoloDetector(config.model)
    selector = TargetSelector(config.target, config.mouse)
    mouse = MouseController(config.mouse)
    hotkeys = Hotkeys()
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

    source.start()
    try:
        while True:
            loop_started = time.perf_counter()
            frame = source.read()
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

            should_move = config.mouse.enabled
            if config.mouse.hold_to_move:
                should_move = should_move and hotkeys.is_down(config.mouse.enable_key)
            if should_move:
                mouse.move_relative(step.dx, step.dy)
                if config.mouse.click_enabled and hotkeys.is_down(config.mouse.click_key):
                    mouse.left_click()

            if config.runtime.preview:
                draw_preview(frame, detections, step.target)
                preview_frame = prepare_preview_frame(frame, preview_scale)
                key = preview_window.show(preview_frame)
                if key == ord(config.runtime.quit_key):
                    break
                if key in {ord("+"), ord("=")}:
                    preview_scale = min(4.0, preview_scale + 0.1)
                    print(f"Preview scale: {preview_scale:.2f}")
                elif key in {ord("-"), ord("_")}:
                    preview_scale = max(0.1, preview_scale - 0.1)
                    print(f"Preview scale: {preview_scale:.2f}")
                elif key == ord("0"):
                    preview_scale = 1.0
                    print("Preview scale: 1.00")

            frame_count += 1
            total_ms = (time.perf_counter() - loop_started) * 1000.0
            if config.runtime.print_fps and frame_count % 15 == 0:
                elapsed = time.perf_counter() - fps_started
                fps = frame_count / max(elapsed, 0.001)
                print(
                    "METRICS "
                    f"inference_ms={inference_ms:.2f} "
                    f"total_ms={total_ms:.2f} "
                    f"fps={fps:.1f} "
                    f"detections={len(detections)} "
                    f"target={int(bool(target))}"
                )
    finally:
        source.stop()
        cv2.destroyAllWindows()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = apply_overrides(load_config(config_path), args)
    run(config)
