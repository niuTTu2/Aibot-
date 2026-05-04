#!/usr/bin/env python3
"""
诊断鼠标控制问题

用法：
    python scripts/diagnose_mouse.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    print("=" * 60)
    print("鼠标控制诊断工具")
    print("=" * 60)

    # 1. 检查配置文件
    print("\n[1] 检查配置文件...")
    config_path = project_root / ".runtime" / "web-console-config.json"
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return

    print(f"✓ 配置文件存在: {config_path}")

    import json
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 2. 检查鼠标配置
    print("\n[2] 检查鼠标配置...")
    mouse_config = config.get("mouse", {})

    print(f"  enabled: {mouse_config.get('enabled')}")
    print(f"  hold_to_move: {mouse_config.get('hold_to_move')}")
    print(f"  backend: {mouse_config.get('backend')}")
    print(f"  enable_keys: {mouse_config.get('enable_keys')}")
    print(f"  movement_mode: {mouse_config.get('movement_mode')}")

    if not mouse_config.get('enabled'):
        print("⚠️  警告：鼠标移动未启用！")

    enable_keys = mouse_config.get('enable_keys', [])
    if not enable_keys:
        print("⚠️  警告：未设置移动热键！")
    else:
        print(f"✓ 移动热键: {', '.join(f'0x{k:02x}' for k in enable_keys)}")

    # 3. 检查后端
    print("\n[3] 检查鼠标后端...")
    backend = mouse_config.get('backend', 'sendinput')

    if backend == 'sendinput':
        print("✓ 使用 Windows SendInput（内置）")
    elif backend == 'lghub_siminput':
        tool_path = mouse_config.get('lghub_tool_path', '')
        print(f"  使用罗技 G HUB siminput")
        print(f"  工具路径: {tool_path}")

        if not Path(tool_path).exists():
            print(f"❌ 工具不存在: {tool_path}")
        else:
            print(f"✓ 工具存在")
    else:
        print(f"⚠️  未知后端: {backend}")

    # 4. 测试导入
    print("\n[4] 测试模块导入...")
    try:
        from yolo_mouse_controller.config import load_config
        print("✓ 配置模块导入成功")
    except Exception as e:
        print(f"❌ 配置模块导入失败: {e}")
        return

    try:
        from yolo_mouse_controller.control.hotkeys import HotkeyMonitor
        print("✓ 热键模块导入成功")
    except Exception as e:
        print(f"❌ 热键模块导入失败: {e}")
        return

    try:
        from yolo_mouse_controller.control.mouse import create_mouse_controller
        print("✓ 鼠标控制模块导入成功")
    except Exception as e:
        print(f"❌ 鼠标控制模块导入失败: {e}")
        return

    # 5. 测试热键监控
    print("\n[5] 测试热键监控...")
    try:
        config_obj = load_config(str(config_path))
        hotkey_monitor = HotkeyMonitor(config_obj.mouse.enable_keys)
        print(f"✓ 热键监控创建成功")
        print(f"  监听热键: {', '.join(f'0x{k:02x}' for k in config_obj.mouse.enable_keys)}")

        # 测试热键状态
        is_down = hotkey_monitor.is_down()
        print(f"  当前状态: {'按下' if is_down else '未按下'}")

    except Exception as e:
        print(f"❌ 热键监控创建失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 6. 测试鼠标控制器
    print("\n[6] 测试鼠标控制器...")
    try:
        mouse = create_mouse_controller(config_obj.mouse)
        print(f"✓ 鼠标控制器创建成功")
        print(f"  后端: {config_obj.mouse.backend}")
        print(f"  可用: {mouse.available}")

        if not mouse.available:
            print(f"❌ 后端不可用: {mouse.last_error}")
        else:
            print(f"✓ 后端可用")

    except Exception as e:
        print(f"❌ 鼠标控制器创建失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 7. 总结
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)

    if not mouse_config.get('enabled'):
        print("\n⚠️  请在 Web 控制台中启用鼠标移动！")
    elif not enable_keys:
        print("\n⚠️  请在 Web 控制台中设置移动热键！")
    elif not mouse.available:
        print(f"\n❌ 鼠标后端不可用: {mouse.last_error}")
    else:
        print("\n✓ 所有检查通过！")
        print("\n测试步骤：")
        print("  1. 启动控制器")
        print(f"  2. 按住热键: {', '.join(f'0x{k:02x}' for k in enable_keys)}")
        print("  3. 查看 Web 控制台的鼠标状态")


if __name__ == "__main__":
    main()
