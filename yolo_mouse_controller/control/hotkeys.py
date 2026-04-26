from __future__ import annotations

import ctypes


class Hotkeys:
    def __init__(self) -> None:
        self.user32 = ctypes.windll.user32

    def is_down(self, virtual_key: int) -> bool:
        return bool(self.user32.GetAsyncKeyState(virtual_key) & 0x8000)
