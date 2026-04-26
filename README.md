# YOLO 鼠标控制器

一个面向 Windows 的 YOLO 视觉鼠标控制器雏形，画面输入支持：

- `dxgi`：单机桌面采集，基于 DXGI/Desktop Duplication，适合本机窗口或全屏画面。
- `capture_card`：采集卡/摄像头，基于 OpenCV 设备号，适合 HDMI 采集卡。

鼠标输出使用 Windows `SendInput`。默认不会自动点击，且只有按住配置里的热键时才移动鼠标，先保证调试时可控。

## 安装

如果 PowerShell 提示 `python` 或 `pip` 找不到，说明系统还没有可用的 Python。推荐直接安装到 `D:\06_Environment\python`：

```powershell
.\scripts\install-python.ps1
```

安装后重新打开 PowerShell，再进入项目目录。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

如果只用采集卡，可以不安装 `dxcam`；如果用 DXGI 单机采集，保留 `dxcam`。

也可以直接用项目脚本，它会自动寻找可用 Python：

```powershell
.\scripts\run.ps1 -Install
.\scripts\run.ps1 -Preview
```

## 快速开始

1. 把自己的 YOLO 权重放到项目目录，例如 `weights/best.pt`。
2. 修改 `config.example.yaml` 里的 `model.path`、目标类别、采集方式。
3. 运行：

```powershell
python -m yolo_mouse_controller --config config.example.yaml
```

常用参数：

```powershell
python -m yolo_mouse_controller --config config.example.yaml --preview
python -m yolo_mouse_controller --config config.example.yaml --source capture_card
python -m yolo_mouse_controller --config config.example.yaml --source dxgi
```

## 配置要点

- `capture.source`
  - `dxgi`：采集当前桌面。
  - `capture_card`：采集卡或摄像头。
- `capture.device_index`
  - 采集卡设备号，通常从 `0`、`1`、`2` 试起。
- `model.path`
  - YOLO `.pt` 权重路径，也可以临时用 `yolov8n.pt` 测试链路。
- `target.class_names`
  - 只跟踪这些类别；空列表表示不过滤类别。
- `mouse.enable_key`
  - 按住该虚拟键码时才移动，默认 `0x06` 是鼠标侧键 XBUTTON2。
- `mouse.click_enabled`
  - 是否允许自动点击，默认 `false`。

## 注意

这个项目只做通用视觉定位和鼠标控制。请只用于你有权限控制的桌面、工具、测试环境或辅助交互场景。
