import numpy as np

from yolo_mouse_controller.capture.crop import center_crop_frame, effective_crop_size


def test_center_crop_frame() -> None:
    frame = np.zeros((100, 200, 3), dtype=np.uint8)

    cropped = center_crop_frame(frame, 50, 40)

    assert cropped.shape[:2] == (40, 50)


def test_zero_crop_size_uses_full_axis() -> None:
    assert effective_crop_size(200, 100, 0, 40) == (200, 40)
