from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CaptureConfig:
    source: str = "dxgi"
    monitor_index: int = 0
    device_index: int = 0
    width: int = 1920
    height: int = 1080
    crop_width: int = 0
    crop_height: int = 0
    fps: int = 60
    region: tuple[int, int, int, int] | None = None


@dataclass
class ModelConfig:
    path: str = "yolov8n.onnx"
    imgsz: int | tuple[int, int] = 640
    conf: float = 0.35
    iou: float = 0.45
    device: str | int | None = 0


@dataclass
class TargetConfig:
    class_names: list[str] = field(default_factory=list)
    prefer_center: bool = True
    # aim_offset_y: 0=顶部(锁头), 0.5=中心(胸), 1=底部 (相对于目标框高度的比例)
    aim_offset_x: float = 0.5
    aim_offset_y: float = 0.5
    max_distance_px: float = 900.0


@dataclass
class TriggerPreset:
    """单个扳机预设，对应一种武器行为。"""
    name: str = "rifle"
    # 开火条件：目标距屏幕中心 <= fire_distance_px 才开火
    fire_distance_px: float = 15.0
    # 开火模式
    # hold  — 按住热键+目标在范围内就持续按住左键（步枪）
    # burst — 每次进入范围触发 burst_count 次点击（连狙/手枪/全自动）
    # semi  — 每次目标进入范围触发一次，目标离开后才能再次触发（半自动）
    # bolt  — 开火一次后等待 bolt_delay_ms 冷却（栓据）
    mode: str = "hold"
    # hold 模式：fire_duration_ms=0 表示一直按住；>0 表示按住N毫秒后松开再按（模拟点射）
    fire_duration_ms: int = 0
    # burst/semi/bolt 模式
    burst_count: int = 1
    burst_interval_ms: int = 80
    bolt_delay_ms: int = 1200
    # 触发热键列表（OR 逻辑，任意一个按下即激活）
    trigger_keys: list[int] = field(default_factory=lambda: [0x05])
    # 武器切换热键（按下此键激活该预设，0=不绑定）
    switch_key: int = 0


# 内置武器预设库
WEAPON_PRESETS: dict[str, TriggerPreset] = {
    "rifle":  TriggerPreset(name="rifle",  mode="hold",  fire_distance_px=15.0, fire_duration_ms=0),
    "sniper": TriggerPreset(name="sniper", mode="semi",  fire_distance_px=8.0,  burst_count=1),
    "pistol": TriggerPreset(name="pistol", mode="burst", fire_distance_px=12.0, burst_count=1, burst_interval_ms=100),
    "bolt":   TriggerPreset(name="bolt",   mode="bolt",  fire_distance_px=8.0,  bolt_delay_ms=1200),
    "auto":   TriggerPreset(name="auto",   mode="burst", fire_distance_px=15.0, burst_count=3, burst_interval_ms=60),
}


@dataclass
class MouseConfig:
    enabled: bool = True
    hold_to_move: bool = True
    backend: str = "sendinput"
    movement_mode: str = "adaptive"
    lghub_tool_path: str = r"D:\02_Workspace\C\mouse\lghub_mouse_tool\build\lghub_siminput_controller.exe"
    lghub_strict: bool = False
    lghub_delay_ms: int = 1
    lghub_flush_interval_ms: int = 8
    # 移动热键（OR 逻辑，任意一个按下即激活瞄准）
    enable_keys: list[int] = field(default_factory=lambda: [0x06])
    sensitivity: float = 0.48
    smoothing: float = 0.55
    deadzone_px: int = 1
    min_step_px: int = 2
    max_step_px: int = 36
    sticky_radius_px: int = 90
    sticky_strength: float = 1.65
    micro_accel: bool = True
    max_step_boost: float = 1.45   # 大误差时步长倍增上限（1.0=不增强）
    # 扳机预设列表（可配置多个，各自绑定不同热键）
    trigger_enabled: bool = False
    triggers: list[TriggerPreset] = field(default_factory=list)
    # Adaptive PD controller params (movement_mode=adaptive)
    kp: float = 0.78
    kp_min: float = 0.26
    kp_curve: float = 0.55
    kd: float = 0.04
    kd_max_ratio: float = 0.15   # D项最大贡献比例（相对max_step），防止鼠标突然移动时D项过大
    # Kalman filter params
    kalman_process_noise: float = 3.5
    kalman_measure_noise: float = 5.0
    kalman_gate_sigma: float = 2.5  # innovation gate 阈值，超过时重置位置（防目标突然移动滞后）
    # Target locking
    lock_target: bool = True        # 锁定目标，防止切换抖动
    lock_miss_frames: int = 2       # 锁定目标消失多少帧后解锁


@dataclass
class RuntimeConfig:
    preview: bool = False
    preview_scale: float = 0.5
    preview_initial_width: int | None = None
    preview_initial_height: int | None = None
    print_fps: bool = True
    quit_key: str = "q"


@dataclass
class AppConfig:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    target: TargetConfig = field(default_factory=TargetConfig)
    mouse: MouseConfig = field(default_factory=MouseConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


def _merge_dataclass(instance: Any, values: dict[str, Any]) -> Any:
    for key, value in values.items():
        # 向后兼容：enable_key (旧) → enable_keys
        if key == "enable_key" and isinstance(instance, MouseConfig):
            instance.enable_keys = [int(value)]
            continue
        # 向后兼容：click_enabled + click_key → triggers
        if key in ("click_enabled", "click_key") and isinstance(instance, MouseConfig):
            continue  # 在 load_config 里统一处理
        if not hasattr(instance, key):
            raise ValueError(f"Unknown config key: {key}")
        current = getattr(instance, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_dataclass(current, value)
        elif key == "triggers" and isinstance(value, list):
            presets = []
            for item in value:
                if isinstance(item, str):
                    # 直接写武器名称字符串，从预设库取
                    p = WEAPON_PRESETS.get(item)
                    if p is None:
                        raise ValueError(f"Unknown weapon preset: {item!r}")
                    presets.append(p)
                elif isinstance(item, dict):
                    # 先从预设库取基础值，再用 dict 覆盖
                    base_name = item.get("name", "rifle")
                    base = WEAPON_PRESETS.get(base_name)
                    if base is not None:
                        import dataclasses
                        preset = dataclasses.replace(base)
                    else:
                        preset = TriggerPreset()
                    _merge_dataclass(preset, item)
                    presets.append(preset)
                else:
                    raise ValueError(f"triggers items must be str or dict, got {type(item)}")
            setattr(instance, key, presets)
        else:
            if key == "device" and isinstance(value, str) and value.isdigit():
                value = int(value)
            setattr(instance, key, value)
    return instance


def load_config(path: str | Path) -> AppConfig:
    import yaml

    cfg = AppConfig()
    with Path(path).open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError("Config file root must be a mapping.")

    # 向后兼容：click_enabled + click_key → triggers
    mouse_data = data.get("mouse", {})
    if isinstance(mouse_data, dict):
        click_enabled = mouse_data.pop("click_enabled", False)
        click_key = mouse_data.pop("click_key", 0x05)
        if click_enabled and "triggers" not in mouse_data:
            mouse_data["triggers"] = [{"name": "pistol", "trigger_keys": [int(click_key)]}]

    return _merge_dataclass(cfg, data)
