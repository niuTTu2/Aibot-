from __future__ import annotations

import ctypes
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

from yolo_mouse_controller.config import MouseConfig

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
SUPPORTED_BACKENDS = {"sendinput", "lghub_siminput"}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _anonymous_ = ("i",)
    _fields_ = [("type", wintypes.DWORD), ("i", _I)]


class MouseController:
    def __init__(self, config: MouseConfig) -> None:
        self.config = config
        self.backend = str(config.backend or "sendinput").lower()
        self.user32 = ctypes.windll.user32
        self.last_error = ""
        self._stream_process: subprocess.Popen[str] | None = None
        self._stream_lock = threading.Lock()
        self._stream_stop = threading.Event()
        self._pending_dx = 0
        self._pending_dy = 0
        self._worker: threading.Thread | None = None
        if self.backend == "lghub_siminput":
            self._start_lghub_stream()

    @property
    def available(self) -> bool:
        if self.backend == "sendinput":
            return True
        if self.backend == "lghub_siminput":
            return self._stream_process is not None and self._stream_process.poll() is None
        return False

    def move_relative(self, dx: int, dy: int) -> bool:
        if not self.config.enabled or (dx == 0 and dy == 0):
            if self.backend == "lghub_siminput":
                self.clear_pending_move()
            return False
        if not self.available:
            return False
        if self.backend == "lghub_siminput":
            return self._queue_lghub_move(dx, dy)
        self._send_mouse(dx, dy, MOUSEEVENTF_MOVE)
        return True

    def left_click(self) -> bool:
        if not self.config.enabled:
            return False
        if not self.available:
            return False
        if self.backend == "lghub_siminput":
            self._flush_lghub_pending()
            return self._send_lghub_command("button click 1")
        self._send_mouse(0, 0, MOUSEEVENTF_LEFTDOWN)
        self._send_mouse(0, 0, MOUSEEVENTF_LEFTUP)
        return True

    def left_press(self) -> bool:
        if not self.config.enabled:
            return False
        if not self.available:
            return False
        if self.backend == "lghub_siminput":
            self._flush_lghub_pending()
            return self._send_lghub_command("button press 1")
        self._send_mouse(0, 0, MOUSEEVENTF_LEFTDOWN)
        return True

    def left_release(self) -> bool:
        if not self.available:
            return False
        if self.backend == "lghub_siminput":
            return self._send_lghub_command("button release 1")
        self._send_mouse(0, 0, MOUSEEVENTF_LEFTUP)
        return True

    def close(self) -> None:
        if self._stream_process is None:
            return
        process = self._stream_process
        self._stream_stop.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=0.5)
        self._flush_lghub_pending(process_override=process)
        self._stream_process = None
        try:
            if process.stdin and process.poll() is None:
                process.stdin.write("release\nquit\n")
                process.stdin.flush()
                process.stdin.close()
        except Exception:
            pass
        try:
            process.wait(timeout=1.0)
        except Exception:
            process.terminate()

    def _start_lghub_stream(self) -> None:
        tool = Path(self.config.lghub_tool_path)
        if not tool.exists():
            self.last_error = f"LGHUB tool not found: {tool}"
            return

        args = [str(tool), "--quiet"]
        if self.config.lghub_strict:
            args.append("--strict")
        args.append("stream")

        try:
            self._stream_process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            self.last_error = f"failed to start LGHUB stream: {exc}"
            self._stream_process = None
            return

        time.sleep(0.08)
        if self._stream_process.poll() is not None:
            self.last_error = f"LGHUB stream exited early with code {self._stream_process.returncode}"
            return
        self._worker = threading.Thread(target=self._lghub_worker, daemon=True)
        self._worker.start()

    def clear_pending_move(self) -> None:
        if self.backend != "lghub_siminput":
            return
        with self._stream_lock:
            self._pending_dx = 0
            self._pending_dy = 0

    def _queue_lghub_move(self, dx: int, dy: int) -> bool:
        if not self.available:
            return False
        # ?????????????LGHUB/??????????????????????
        # ??????????????????????????????????????
        with self._stream_lock:
            self._pending_dx = int(dx)
            self._pending_dy = int(dy)
        return True

    def _lghub_worker(self) -> None:
        interval = max(0.001, int(self.config.lghub_flush_interval_ms) / 1000.0)
        while not self._stream_stop.is_set():
            self._flush_lghub_pending()
            time.sleep(interval)
        self._flush_lghub_pending()

    def _flush_lghub_pending(self, process_override: subprocess.Popen[str] | None = None) -> bool:
        with self._stream_lock:
            dx = self._pending_dx
            dy = self._pending_dy
            self._pending_dx = 0
            self._pending_dy = 0
        if dx == 0 and dy == 0:
            return True
        return self._send_lghub_command(
            f"move {dx} {dy} {max(0, int(self.config.lghub_delay_ms))}",
            process_override=process_override,
        )

    def _send_lghub_command(self, command: str, process_override: subprocess.Popen[str] | None = None) -> bool:
        process = process_override or self._stream_process
        if process is None or process.poll() is not None or process.stdin is None:
            self.last_error = "LGHUB stream is not running"
            return False
        try:
            process.stdin.write(command + "\n")
            process.stdin.flush()
            return True
        except Exception as exc:
            self.last_error = f"failed to write LGHUB stream command: {exc}"
            return False

    def _send_mouse(self, dx: int, dy: int, flags: int) -> None:
        mouse_input = MOUSEINPUT(dx, dy, 0, flags, 0, None)
        input_struct = INPUT(INPUT_MOUSE, INPUT._I(mi=mouse_input))
        size = ctypes.sizeof(INPUT)
        sent = self.user32.SendInput(1, ctypes.byref(input_struct), size)
        if sent != 1:
            raise ctypes.WinError()

    def __del__(self) -> None:
        self.close()
