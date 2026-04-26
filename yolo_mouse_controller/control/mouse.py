from __future__ import annotations

import ctypes
from ctypes import wintypes

from yolo_mouse_controller.config import MouseConfig

from .hotkeys import Hotkeys

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


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
        self.user32 = ctypes.windll.user32

    def move_relative(self, dx: int, dy: int) -> None:
        if not self.config.enabled or (dx == 0 and dy == 0):
            return
        self._send_mouse(dx, dy, MOUSEEVENTF_MOVE)

    def left_click(self) -> None:
        if not self.config.enabled or not self.config.click_enabled:
            return
        self._send_mouse(0, 0, MOUSEEVENTF_LEFTDOWN)
        self._send_mouse(0, 0, MOUSEEVENTF_LEFTUP)

    def _send_mouse(self, dx: int, dy: int, flags: int) -> None:
        mouse_input = MOUSEINPUT(dx, dy, 0, flags, 0, None)
        input_struct = INPUT(INPUT_MOUSE, INPUT._I(mi=mouse_input))
        size = ctypes.sizeof(INPUT)
        sent = self.user32.SendInput(1, ctypes.byref(input_struct), size)
        if sent != 1:
            raise ctypes.WinError()
