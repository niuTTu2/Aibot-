from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class FrameSource(ABC):
    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def read(self) -> np.ndarray | None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

class ThreadedFrameSource(FrameSource):
    """
    独立采集线程封装器 (流水线化)。
    解耦了 OpenCV 或 DXGI 读取阻塞对系统主控制循环的延迟惩罚。
    采用容量为 1 的无阻塞队列设计，确保推理流水线永远只处理"极其最新"的一帧。
    """
    def __init__(self, source: FrameSource):
        import queue
        import threading
        self._source = source
        self._q = queue.Queue(maxsize=1)
        self._running = False
        self._thread = threading.Thread(target=self._worker, daemon=True)

    def _worker(self):
        while self._running:
            frame = self._source.read()
            if frame is not None:
                # 满则非阻塞弹出旧帧，永远保持最新
                if self._q.full():
                    try:
                        self._q.get_nowait()
                    except:
                        pass
                try:
                    self._q.put_nowait(frame)
                except:
                    pass

    def start(self) -> None:
        self._source.start()
        self._running = True
        self._thread.start()

    def read(self) -> np.ndarray | None:
        try:
            # 短暂阻塞获取，如果没帧不卡顿主线程超过10ms
            return self._q.get(timeout=0.010)
        except Exception:
            return None

    def stop(self) -> None:
        self._running = False
        self._source.stop()
        if self._thread.is_alive():
            try:
                self._thread.join(timeout=1.0)
            except:
                pass
