from yolo_mouse_controller.config import MouseConfig, _merge_dataclass


def test_mouse_legacy_pressure_strength_maps_to_sticky_strength() -> None:
    mouse = MouseConfig(sticky_strength=1.65)
    _merge_dataclass(mouse, {"pressure_strength": 2.1})
    assert mouse.sticky_strength == 2.1


def test_mouse_unknown_key_is_ignored() -> None:
    mouse = MouseConfig()
    _merge_dataclass(mouse, {"unknown_field_abc": 123})
    assert mouse.enabled is True
