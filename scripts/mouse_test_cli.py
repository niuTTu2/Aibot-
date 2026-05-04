from __future__ import annotations

import ctypes
import json
import math
import sys
import threading
import time
import argparse
import subprocess
from pathlib import Path


def emit(ok: bool, **values: object) -> int:
    values["ok"] = ok
    print(json.dumps(values, ensure_ascii=True))
    return 0 if ok else 1


def screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def cursor_position() -> tuple[int, int]:
    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    point = Point()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def set_cursor(x: float, y: float) -> None:
    ctypes.windll.user32.SetCursorPos(int(round(x)), int(round(y)))


class MouseMover:
    def move_to(self, target_x: int, target_y: int) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class SendInputMover(MouseMover):
    def move_to(self, target_x: int, target_y: int) -> None:
        move_to_with_setcursor(target_x, target_y)


class LghubStreamMover(MouseMover):
    def __init__(self, tool_path: str, strict: bool, delay_ms: int) -> None:
        tool = Path(tool_path)
        if not tool.exists():
            raise FileNotFoundError(f"LGHUB tool not found: {tool}")
        args = [str(tool), "--quiet"]
        if strict:
            args.append("--strict")
        args.append("stream")
        self.delay_ms = max(0, int(delay_ms))
        self.process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def move_to(self, target_x: int, target_y: int) -> None:
        if self.process.poll() is not None or self.process.stdin is None:
            raise RuntimeError("LGHUB stream is not running")
        
        start_x, start_y = cursor_position()
        steps = 25
        for step in range(1, steps + 1):
            t = step / steps
            eased = 1.0 - math.pow(1.0 - t, 3)
            path_x = start_x + (target_x - start_x) * eased
            path_y = start_y + (target_y - start_y) * eased
            
            current_x, current_y = cursor_position()
            # Calculate raw pixel difference to our current path target
            diff_x = path_x - current_x
            diff_y = path_y - current_y
            
            # Dampen the translation to mickeys to prevent acceleration overshoot
            dx = int(round(diff_x * 0.45))
            dy = int(round(diff_y * 0.45))
            
            if dx != 0 or dy != 0:
                self._move_relative(dx, dy)
            time.sleep(0.015)
            
        # Final fine-tuning
        for _ in range(5):
            current_x, current_y = cursor_position()
            dx = int((target_x - current_x) * 0.3)
            dy = int((target_y - current_y) * 0.3)
            if dx == 0 and dy == 0:
                break
            self._move_relative(dx, dy)
            time.sleep(0.02)

    def _move_relative(self, dx: int, dy: int) -> None:
        if self.process.poll() is not None or self.process.stdin is None:
            raise RuntimeError("LGHUB stream is not running")
        self.process.stdin.write(f"move {dx} {dy} {self.delay_ms}\n")
        self.process.stdin.flush()

    def close(self) -> None:
        try:
            if self.process.stdin and self.process.poll() is None:
                self.process.stdin.write("release\nquit\n")
                self.process.stdin.flush()
                self.process.stdin.close()
        except Exception:
            pass
        try:
            self.process.wait(timeout=1.0)
        except Exception:
            self.process.terminate()


def move_to_with_setcursor(target_x: int, target_y: int, duration: float = 0.42, steps: int = 36) -> None:
    start_x, start_y = cursor_position()
    for step in range(1, steps + 1):
        t = step / steps
        eased = 1.0 - math.pow(1.0 - t, 3)
        x = start_x + (target_x - start_x) * eased
        y = start_y + (target_y - start_y) * eased
        set_cursor(x, y)
        time.sleep(duration / steps)


def run_overlay(mover: MouseMover) -> None:
    import tkinter as tk

    errors: list[str] = []
    width, height = screen_size()
    radius = max(72, min(width, height) // 10)
    points = [
        (round(width * 0.28), round(height * 0.36)),
        (round(width * 0.72), round(height * 0.36)),
        (round(width * 0.50), round(height * 0.66)),
    ]

    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{width}x{height}+0+0")
    root.attributes("-topmost", True)
    root.configure(bg="black")
    try:
        root.attributes("-transparentcolor", "black")
    except tk.TclError:
        root.attributes("-alpha", 0.88)

    canvas = tk.Canvas(root, width=width, height=height, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    colors = ["#22c55e", "#38bdf8", "#f59e0b"]
    for index, ((x, y), color) in enumerate(zip(points, colors), start=1):
        canvas.create_oval(x - radius, y - radius, x + radius, y + radius, outline=color, width=9)
        canvas.create_oval(x - 8, y - 8, x + 8, y + 8, fill=color, outline="")
        canvas.create_text(x, y - radius - 34, text=str(index), fill=color, font=("Segoe UI", 32, "bold"))

    def runner() -> None:
        time.sleep(0.35)
        try:
            for x, y in points:
                mover.move_to(x, y)
                time.sleep(0.26)
        except Exception as exc:
            errors.append(str(exc))
        finally:
            mover.close()
            time.sleep(0.65)
            root.after(0, root.destroy)

    threading.Thread(target=runner, daemon=True).start()
    root.mainloop()
    if errors:
        raise RuntimeError(errors[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Mouse movement test")
    parser.add_argument("--backend", default="sendinput")
    parser.add_argument("--tool", default=r"D:\02_Workspace\C\mouse\lghub_mouse_tool\build\lghub_siminput_controller.exe")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--delay", type=int, default=1)
    args = parser.parse_args()
    backend = str(args.backend or "sendinput").lower()

    if backend not in {"sendinput", "lghub_siminput"}:
        return emit(
            True,
            skipped=True,
            backend=backend,
            message=f"mouse test skipped because backend '{backend}' is not implemented",
        )

    if not sys.platform.startswith("win"):
        return emit(False, error="mouse test is only supported on Windows")
    try:
        mover: MouseMover
        if backend == "lghub_siminput":
            mover = LghubStreamMover(args.tool, args.strict, args.delay)
        else:
            mover = SendInputMover()
        run_overlay(mover)
    except Exception as exc:
        return emit(False, error=str(exc))
    return emit(True, backend=backend, message="mouse movement test completed")


if __name__ == "__main__":
    raise SystemExit(main())
