# YOLO 鼠标控制器

重新编译：
cd "D:\Niu\Documents\New project"

Get-Process yolo_web_console -ErrorAction SilentlyContinue | Stop-Process -Force

$mingw = "D:\06_Environment\Cpp\mingw64\bin"
$env:PATH = "$mingw;$env:PATH"

& "$mingw\g++.exe" -std=c++17 -O2 -static -static-libgcc -static-libstdc++ -o native_console\yolo_web_console.exe native_console\server.cpp -lws2_32 -lshell32 -lcomdlg32

.\native_console\yolo_web_console.exe --root "D:\Niu\Documents\New project" --port 8765




这是一个 Windows 本地部署的 YOLO 视觉鼠标控制项目，支持 DXGI 单机画面采集、采集卡输入、`.pt` / `.onnx` 模型、浏览器控制台、鼠标移动测试、推理设备扫描和运行日志监控。

项目根目录：

```text
D:\Niu\Documents\New project
```

> 说明：下面命令不会修改 `D:\06_Environment`。`D:\06_Environment\Cpp\mingw64\bin` 只作为 MinGW 编译器和运行时 DLL 的读取路径使用。

---

## 1. 项目结构说明

```text
native_console\server.cpp              C++ 本地 HTTP 服务端
native_console\yolo_web_console.exe    编译后的浏览器控制台服务
web_console\index.html                 浏览器 UI 页面
web_console\styles.css                 浏览器 UI 样式
web_console\app.js                     浏览器 UI 交互逻辑
scripts\web-console.ps1                启动 Web 控制台脚本
scripts\build-web-console.ps1          构建 Web 控制台脚本
scripts\model_info_cli.py              读取模型类别和 ONNX 输入尺寸
scripts\device_info_cli.py             扫描推理设备
scripts\mouse_test_cli.py              鼠标移动测试，屏幕画 3 个大圈
yolo_mouse_controller\                 Python YOLO 鼠标控制器主体
config.example.yaml                     示例配置
requirements.txt                        Python 依赖
```

---

## 2. 电脑重启后如何启动项目

如果电脑重启后，只想正常使用项目，按下面步骤执行。

### 方法 A：直接启动已编译好的 Web 控制台

打开 PowerShell：

```powershell
cd "D:\Niu\Documents\New project"

$mingw = "D:\06_Environment\Cpp\mingw64\bin"
$env:PATH = "$mingw;$env:PATH"

.\native_console\yolo_web_console.exe --root "D:\Niu\Documents\New project" --port 8765
```

然后浏览器打开：

```text
http://127.0.0.1:8765/
```

如果页面没有自动刷新到最新版，请按：

```text
Ctrl + F5
```

### 方法 B：使用启动脚本

```powershell
cd "D:\Niu\Documents\New project"
powershell -ExecutionPolicy Bypass -File .\scripts\web-console.ps1
```

浏览器地址仍然是：

```text
http://127.0.0.1:8765/
```

---

## 3. 修改代码或新增文件后如何处理

不同类型的文件处理方式不一样。

### 3.1 修改 Python 文件后

例如修改了：

```text
yolo_mouse_controller\app.py
yolo_mouse_controller\config.py
yolo_mouse_controller\control\targeting.py
yolo_mouse_controller\control\mouse.py
scripts\mouse_test_cli.py
scripts\device_info_cli.py
scripts\model_info_cli.py
```

Python 文件不需要 C++ 编译。处理步骤：

1. 停止当前控制器或关闭 Web 控制台。
2. 重新启动 Web 控制台。
3. 在浏览器里重新点击“启动控制器”。

可选语法检查：

```powershell
cd "D:\Niu\Documents\New project"
python -m py_compile `
  .\yolo_mouse_controller\app.py `
  .\yolo_mouse_controller\config.py `
  .\yolo_mouse_controller\control\targeting.py `
  .\yolo_mouse_controller\control\mouse.py `
  .\scripts\mouse_test_cli.py `
  .\scripts\device_info_cli.py `
  .\scripts\model_info_cli.py
```

### 3.2 修改 Web 前端文件后

例如修改了：

```text
web_console\index.html
web_console\styles.css
web_console\app.js
```

前端文件不需要重新编译 C++。处理步骤：

1. 保持 `yolo_web_console.exe` 运行即可。
2. 浏览器按 `Ctrl + F5` 强制刷新。

如果页面仍然不是最新版，重启 Web 控制台：

```powershell
cd "D:\Niu\Documents\New project"
$mingw = "D:\06_Environment\Cpp\mingw64\bin"
$env:PATH = "$mingw;$env:PATH"
.\native_console\yolo_web_console.exe --root "D:\Niu\Documents\New project" --port 8765
```

### 3.3 修改 C++ 服务端后

只要修改了：

```text
native_console\server.cpp
```

就必须重新编译 `yolo_web_console.exe`。

推荐使用静态编译，避免启动时报：

```text
libstdc++-6.dll 找不到
libgcc_s_seh-1.dll 找不到
```

编译命令：

```powershell
cd "D:\Niu\Documents\New project"

$mingw = "D:\06_Environment\Cpp\mingw64\bin"
$env:PATH = "$mingw;$env:PATH"

& "$mingw\g++.exe" -std=c++17 -O2 -static -static-libgcc -static-libstdc++ -o native_console\yolo_web_console.exe native_console\server.cpp -lws2_32 -lshell32 -lcomdlg32
```

编译成功后启动：

```powershell
.\native_console\yolo_web_console.exe --root "D:\Niu\Documents\New project" --port 8765
```

然后浏览器打开：

```text
http://127.0.0.1:8765/
```

---

## 4. 从零启动完整流程

适合电脑重启、服务关闭、或者不确定当前状态时使用。

```powershell
cd "D:\Niu\Documents\New project"

$mingw = "D:\06_Environment\Cpp\mingw64\bin"
$env:PATH = "$mingw;$env:PATH"

.\native_console\yolo_web_console.exe --root "D:\Niu\Documents\New project" --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765/
```

进入页面后：

1. 左侧进入“模型”。
2. 选择模型 `.pt` 或 `.onnx`。
3. 点击“读取类别”。
4. 点击“扫描设备”。
5. 如果当前 Python 是 CPU 版 PyTorch，请选择 `CPU`，不要选择 `0`。
6. 进入“采集”，设置 DXGI 或采集卡。
7. 进入“鼠标”，选择鼠标移动方式。
8. 点击“保存配置”。
9. 点击“启动控制器”。

---

## 5. 推理设备选择说明

如果日志出现：

```text
torch.cuda.is_available(): False
torch.cuda.device_count(): 0
Invalid CUDA 'device=0' requested
```

说明当前环境没有可用 CUDA。此时在浏览器控制台中：

```text
模型 -> 推理设备 -> CPU
```

然后保存配置并重新启动控制器。

常见选择：

```text
Auto    自动选择
CPU     强制 CPU 推理
0       第一张 CUDA GPU，仅在 CUDA 可用时使用
```

---

## 6. 鼠标控制说明

当前鼠标移动后端使用 Windows 原生 API：

```text
user32.SendInput
```

移动方式是相对移动：

```text
MOUSEEVENTF_MOVE
```

点击方式是：

```text
MOUSEEVENTF_LEFTDOWN
MOUSEEVENTF_LEFTUP
```

浏览器“鼠标”页面现在分为两个概念：

鼠标控制后端：

```text
Windows SendInput sendinput          已实现，当前默认
罗技 G HUB siminput lghub_siminput   已实现，stream 模式
罗技驱动直连 logitech_driver         实验预留，当前未接入主流程
罗技 G HUB Lua logitech_lua          预留选项
HID 串口设备 hid_serial              预留选项
```

移动曲线：

```text
平滑跟随 smooth
直接移动 direct
缓动稳定 eased
分段控速 stepped
```

`lghub_siminput` 需要先确认 Logitech G HUB / `lghub_agent.exe` 正在运行，并且工具路径指向：

```text
D:\02_Workspace\C\mouse\lghub_mouse_tool\build\lghub_siminput_controller.exe
```

该后端会以 stream 模式启动：

```text
lghub_siminput_controller.exe --quiet --strict stream
```

移动时持续写入：

```text
move dx dy delay_ms
button click 1
release
quit
```

如果选择未接入的后端，控制器会显示 `backend_unavailable`，不会发送真实鼠标移动。

鼠标页面下方有独立日志，会显示：

```text
MOUSE_STATUS ...
MOUSE_CMD ...
```

例如：

```text
MOUSE_STATUS state=waiting_hotkey enabled=true hold_to_move=true hotkey_down=false backend=sendinput backend_ready=true mode=smooth target=none step_dx=0 step_dy=0
MOUSE_CMD type=move backend=sendinput dx=14 dy=-6 mode=smooth target=person:0.86
```

---

## 7. 鼠标移动测试

浏览器进入：

```text
鼠标 -> 鼠标移动测试
```

点击后会：

1. 在屏幕上画 3 个大圈。
2. 自动把鼠标移动到三个圈的位置。
3. 在鼠标专属日志里输出测试状态。

如果点击后显示 `not found`，说明你运行的是旧版 `yolo_web_console.exe`。重新编译 `native_console\server.cpp` 后再启动。

---

## 8. 常见问题

### 8.1 找不到 libstdc++-6.dll 或 libgcc_s_seh-1.dll

不要双击 exe。使用 PowerShell 启动：

```powershell
cd "D:\Niu\Documents\New project"
$mingw = "D:\06_Environment\Cpp\mingw64\bin"
$env:PATH = "$mingw;$env:PATH"
.\native_console\yolo_web_console.exe --root "D:\Niu\Documents\New project" --port 8765
```

或者重新静态编译：

```powershell
cd "D:\Niu\Documents\New project"
$mingw = "D:\06_Environment\Cpp\mingw64\bin"
$env:PATH = "$mingw;$env:PATH"
& "$mingw\g++.exe" -std=c++17 -O2 -static -static-libgcc -static-libstdc++ -o native_console\yolo_web_console.exe native_console\server.cpp -lws2_32 -lshell32 -lcomdlg32
```

### 8.2 修改前端后页面没变化

浏览器按：

```text
Ctrl + F5
```

### 8.3 修改 C++ 后接口还是 not found

说明没有重新编译，或者启动的还是旧 exe。重新执行第 3.3 节的编译命令。

### 8.4 修改 Python 后没生效

停止控制器，再重新点击“启动控制器”。如果仍不生效，关闭 `yolo_web_console.exe` 后重新启动。
