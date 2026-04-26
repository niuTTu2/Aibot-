from yolo_mouse_controller.vision.model_info import format_imgsz, normalize_imgsz


def test_normalize_square_imgsz() -> None:
    assert normalize_imgsz(256) == 256


def test_normalize_rectangular_imgsz() -> None:
    assert normalize_imgsz([256, 320]) == (256, 320)


def test_format_imgsz() -> None:
    assert format_imgsz(256) == "256x256"
    assert format_imgsz((256, 320)) == "256x320"
