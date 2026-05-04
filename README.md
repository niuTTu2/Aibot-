# YOLO Mouse Controller

一个面向 Windows 的 YOLO 鼠标控制项目，支持：

- DXGI 单机画面采集
- 采集卡 / 摄像头输入
- `.pt` / `.onnx` / `.trt` / `.engine` 模型
- 本地 C++ Web 控制台
- 浏览器可视化配置
- 鼠标移动测试、设备扫描、日志与实时指标

---

## 一键启动（小白版）

### 方法 1：双击启动（最简单）

直接双击项目根目录里的：

```text
一键启动-Web控制台.bat
```

它会自动：

1. 启动本地 Web 控制台
2. 打开浏览器
3. 进入：

```text
http://127.0.0.1:8765/
```

如果页面样式没刷新出来，按一次：

```text
Ctrl + F5
```

---

### 方法 2：命令行启动

```powershell
cd "D:\Niu\Documents\New project"
powershell -ExecutionPolicy Bypass -File .\scripts\web-console.ps1
```

浏览器打开：

```text
http://127.0.0.1:8765/
```

---

## 重启电脑后怎么再次启动

重启系统后，不需要重新编译，也不需要重新安装环境。

你只要：

1. 进入项目目录
2. 双击 `一键启动-Web控制台.bat`
3. 浏览器里进入控制台页面
4. 点击页面里的“启动控制器”

就可以继续使用。

---

## 项目目录说明（重构后）

```text
D:\Niu\Documents\New project
├─ artifacts/                    # 运行产物、日志、打包输出、性能分析文件
│  ├─ logs/
│  ├─ profiles/
│  └─ pyinstaller/
│     ├─ build/
│     └─ dist/
├─ configs/                      # 配置文件
│  └─ config.example.yaml
├─ docs/                         # 项目文档
│  └─ gpu-runtime-notes.txt
├─ models/                       # 模型目录
│  ├─ sample/                    # 示例模型
│  └─ local/                     # 你自己的本地模型（建议放这里）
├─ native_console/               # C++ 本地 Web 服务端
│  ├─ server.cpp
│  ├─ yolo_web_console.exe
│  └─ dev_artifacts/             # C++ 开发过程中的中间文件
├─ packaging/
│  └─ pyinstaller/
│     └─ yolo_mouse_controller.spec
├─ scripts/                      # 启动、构建、辅助工具脚本
│  ├─ run.ps1
│  ├─ web-console.ps1
│  ├─ build-web-console.ps1
│  ├─ build-exe.ps1
│  ├─ device_info_cli.py
│  ├─ model_info_cli.py
│  └─ mouse_test_cli.py
├─ tests/
│  └─ manual/                    # 手工测试脚本
├─ web_console/                  # 浏览器前端
│  ├─ index.html
│  ├─ styles.css
│  └─ app.js
├─ yolo_mouse_controller/        # Python 主程序
├─ Start-WebConsole.bat          # 英文启动入口
├─ 一键启动-Web控制台.bat        # 中文一键启动入口
├─ pyproject.toml
├─ requirements.txt
└─ README.md
```

---

## 目录使用规范

### 1）模型怎么放

- 示例模型放在：

```text
models/sample/
```

- 你自己的模型建议放在：

```text
models/local/
```

例如：

```text
models/local/xiaohuamaoV8_640_fp16.trt
models/local/xiaohuamaoV8_640_fp16.onnx
```

这样以后换模型、备份项目、提交代码都更清晰。

---

### 2）配置文件放哪里

- 标准示例配置：

```text
configs/config.example.yaml
```

- 控制台运行时生成配置：

```text
.runtime/web-console-config.json
```

如果你是通过网页控制台启动，一般不需要手动改 `.runtime` 下的文件。

---

### 3）日志、测试、打包输出放哪里

- 日志：`artifacts/logs/`
- 性能分析：`artifacts/profiles/`
- PyInstaller 输出：`artifacts/pyinstaller/`
- 手工测试脚本：`tests/manual/`

这样根目录不会再堆很多零散文件。

---

## 开发环境安装

### Python 依赖安装

```powershell
cd "D:\Niu\Documents\New project"
.\scripts\run.ps1 -Install
```

### 启动 Python 预览模式

```powershell
cd "D:\Niu\Documents\New project"
.\scripts\run.ps1 -Preview
```

### 启动 Web 控制台

```powershell
cd "D:\Niu\Documents\New project"
.\scripts\web-console.ps1
```

---

## 修改代码后如何处理

### 改了 Python 代码后

比如你改了这些：

```text
yolo_mouse_controller/app.py
yolo_mouse_controller/config.py
yolo_mouse_controller/control/targeting.py
yolo_mouse_controller/control/mouse.py
scripts/model_info_cli.py
scripts/device_info_cli.py
```

一般 **不需要重新编译 C++ 服务端**。

你只要：

1. 停止当前控制器
2. 重新点击网页里的“启动控制器”

如果是直接命令行运行的，就重新执行一次 `run.ps1`。

---

### 改了前端页面后

比如改了：

```text
web_console/index.html
web_console/styles.css
web_console/app.js
```

处理方式：

1. 保持服务端运行即可
2. 浏览器按：

```text
Ctrl + F5
```

强制刷新页面。

如果还是旧页面，就关掉标签页重新打开 `http://127.0.0.1:8765/`。

---

### 改了 C++ 服务端后

比如改了：

```text
native_console/server.cpp
```

需要重新编译：

```powershell
cd "D:\Niu\Documents\New project"
.\scripts\build-web-console.ps1
```

然后重新启动：

```powershell
.\scripts\web-console.ps1
```

---

## 构建说明

### 构建本地 Web 控制台（C++）

```powershell
cd "D:\Niu\Documents\New project"
.\scripts\build-web-console.ps1
```

输出文件：

```text
native_console/yolo_web_console.exe
```

---

### 打包 Python EXE

```powershell
cd "D:\Niu\Documents\New project"
.\scripts\build-exe.ps1
```

输出目录：

```text
artifacts/pyinstaller/dist/
```

---

## 推荐开发流程

### 日常使用

- 双击 `一键启动-Web控制台.bat`
- 浏览器里调参数
- 点“启动控制器”

### 调试 Python

- `.\scripts\run.ps1 -Preview`
- 看预览窗口和控制台输出

### 改前端

- 改 `web_console/`
- 浏览器 `Ctrl + F5`

### 改服务端

- 改 `native_console/server.cpp`
- 重新执行 `.\scripts\build-web-console.ps1`

---

## 注意事项

- 本项目不会修改 `D:\06_Environment` 里的文件。
- `D:\06_Environment\python\python.exe` 和 `D:\06_Environment\Cpp\mingw64\bin` 只作为现有工具链使用。
- 如果页面空白，优先检查：
  - 服务是否正常启动
  - 浏览器是否 `Ctrl + F5`
  - 启动参数里的 `--root` 是否正确

---

## 当前推荐入口

如果你只是正常使用项目，直接双击：

```text
一键启动-Web控制台.bat
```

这是给小白最省事的方式。

