from yolo_mouse_controller.config import MouseConfig, TargetConfig
from yolo_mouse_controller.control.targeting import TargetSelector
from yolo_mouse_controller.vision import Detection


def test_selects_nearest_allowed_target() -> None:
    selector = TargetSelector(TargetConfig(class_names=["person"]), MouseConfig())
    detections = [
        Detection((10, 10, 50, 50), 0.99, 0, "person"),
        Detection((300, 220, 340, 260), 0.50, 0, "person"),
        Detection((320, 240, 360, 280), 0.99, 1, "car"),
    ]

    target = selector.select(detections, frame_width=640, frame_height=480)

    assert target is not None
    assert target.class_name == "person"
    assert target.xyxy == (300, 220, 340, 260)


def test_aim_step_applies_deadzone() -> None:
    mouse = MouseConfig(sensitivity=1.0, smoothing=0.0, deadzone_px=5)
    selector = TargetSelector(TargetConfig(), mouse)
    target = Detection((322, 242, 326, 246), 0.9, 0, "target")

    step = selector.aim_step(target, frame_width=640, frame_height=480)

    assert step.dx == 0
    assert step.dy == 0


def test_can_prefer_highest_confidence() -> None:
    selector = TargetSelector(TargetConfig(prefer_center=False), MouseConfig())
    detections = [
        Detection((300, 220, 340, 260), 0.50, 0, "target"),
        Detection((10, 10, 50, 50), 0.99, 0, "target"),
    ]

    target = selector.select(detections, frame_width=640, frame_height=480)

    assert target is not None
    assert target.confidence == 0.99
