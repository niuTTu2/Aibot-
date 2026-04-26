from __future__ import annotations

import numpy as np


def center_crop_frame(frame: np.ndarray, crop_width: int, crop_height: int) -> np.ndarray:
    frame_height, frame_width = frame.shape[:2]
    crop_width = _normalize_crop_size(crop_width, frame_width)
    crop_height = _normalize_crop_size(crop_height, frame_height)
    if crop_width == frame_width and crop_height == frame_height:
        return frame

    left = max(0, (frame_width - crop_width) // 2)
    top = max(0, (frame_height - crop_height) // 2)
    return frame[top : top + crop_height, left : left + crop_width]


def effective_crop_size(source_width: int, source_height: int, crop_width: int, crop_height: int) -> tuple[int, int]:
    return _normalize_crop_size(crop_width, source_width), _normalize_crop_size(crop_height, source_height)


def _normalize_crop_size(value: int, full_size: int) -> int:
    if value <= 0:
        return full_size
    return max(1, min(value, full_size))
