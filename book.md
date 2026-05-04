# YOLO Mouse Controller Book

本文是对整个仓库的归档总结，目标是把代码的入口、控制器、逻辑、原理、算法、控制台和测试一次性梳理清楚，方便后续维护、排障和二次开发。

## 1. 项目定位

这是一个面向 Windows 的本地 YOLO 视觉鼠标控制项目。核心能力分成四段：

1. 采集屏幕或采集卡画面。
2. 用 YOLO 模型做目标检测。
3. 通过目标选择与瞄准算法计算鼠标步长。
4. 把鼠标动作输出到 Windows SendInput 或 Logitech G HUB siminput。

整套系统被 Web 控制台、Python 主控制器、C++ 宿主进程串起来。Web 控制台负责配置、启动、停止、查看日志和运行指标；Python 负责业务控制循环；C++ 宿主负责把静态前端、进程生命周期、模型信息、设备扫描、鼠标测试这些杂项统一接起来。

## 2. 总体架构

主链路可以概括成：

`web_console -> native_console/server.cpp -> yolo_mouse_controller/app.py -> capture -> vision -> control -> mouse`

核心数据流如下：

1. `native_console/server.cpp` 提供本地 HTTP 服务和静态资源。
2. 浏览器页面 `web_console/index.html` + `web_console/app.js` 发起 API 请求。
3. 服务器保存配置、启动 Python 主程序、转发日志、解析指标。
4. `yolo_mouse_controller.app.run()` 拉起采集源、模型、目标选择器、鼠标控制器、热键和扳机线程。
5. 采集帧进入检测器，得到 `Detection` 列表。
6. `ElegantAimController` 选择目标并计算鼠标步长。
7. `MouseController` 把步长输出到系统鼠标或 Logitech 后端。

## 3. 入口与启动方式

### 3.1 Python 入口

Python 的入口在 `yolo_mouse_controller/__main__.py`，它只是调用 `yolo_mouse_controller.app.main()`。

`yolo_mouse_controller/app.py` 是真正的业务入口。它负责：

1. 解析命令行参数。
2. 读取配置文件。
3. 创建采集源、检测器、目标控制器、鼠标控制器、热键和扳机控制器。
4. 进入主循环。

### 3.2 Web 控制台入口

`native_console/server.cpp` 是浏览器控制台的宿主进程。它监听 `127.0.0.1:8765`，启动浏览器，提供 `/api/*` 接口，并把 Python 控制器作为子进程拉起。

### 3.3 辅助脚本入口

仓库中还有几个单独的 CLI：

1. `scripts/model_info_cli.py`：读取模型类别和固定输入尺寸。
2. `scripts/device_info_cli.py`：扫描推理设备与可用 provider。
3. `scripts/mouse_test_cli.py`：鼠标移动测试。
4. `scripts/benchmark_models.py`：做模型基准测试。

## 4. 配置系统

配置定义在 `yolo_mouse_controller/config.py`，以 dataclass 组织：

1. `CaptureConfig`：采集源、显示器编号、采集卡编号、宽高、FPS、裁剪区域。
2. `ModelConfig`：模型路径、输入尺寸、置信度、IOU、设备选择。
3. `TargetConfig`：类别过滤、是否优先靠近中心、瞄准点偏移、最大锁定距离。
4. `MouseConfig`：鼠标后端、移动曲线、灵敏度、平滑、死区、步长限制、Kalman 参数、目标锁定、扳机和武器切换设置。
5. `RuntimeConfig`：预览窗口、缩放比例、是否打印 FPS、退出键。

`load_config()` 支持旧字段兼容：

1. `enable_key` 会折叠成 `enable_keys`。
2. 旧的点击配置会折叠成 `triggers`。
3. 一些废弃字段会被忽略，以便前端老配置还能继续启动。

## 5. 采集子系统

采集相关代码在 `yolo_mouse_controller/capture/`。

### 5.1 抽象接口

`capture/base.py` 定义了 `FrameSource` 抽象基类，统一要求：

1. `start()`
2. `read()`
3. `stop()`
4. `ThreadedFrameSource` 封装：对任何实际信号源做分离线程的无阻塞抓取（Queue length=1 不断清理旧帧丢弃），避免因单次屏幕 API 或 OpenCV 截图耗时影响到 Python 推理主线流水线卡顿。这是 v2 降低采集隐形延时的核心结构之一。

### 5.2 采集工厂

`capture/factory.py` 根据 `CaptureConfig.source` 在两种实现之间切换：

1. `dxgi` -> `DxgiSource`
2. `capture_card` / `card` / `camera` / `opencv` -> `CaptureCardSource`

### 5.3 DXGI 桌面采集

`capture/dxgi.py` 使用 `dxcam` 做桌面采集。它的要点是：

1. 创建 DXGI 采集对象。
2. 如果用户没有显式给 `region`，则根据 `crop_width` / `crop_height` 计算中心裁剪区域。
3. 以 `target_fps` 和 `video_mode=True` 启动。

这条路径适合单机显示器画面采集。

### 5.4 采集卡 / 摄像头采集

`capture/capture_card.py` 使用 OpenCV 的 `VideoCapture`。
相比传统的 DirectShow，目前已升级为首选 `CAP_MSMF` 无缓冲采集降低底层链路积压：

1. 优先采用 `CAP_MSMF` 建立低延迟连接通道。
2. 设置输入宽高与 FPS。
3. 把缓冲区压到 1 帧，尽量降低延迟。
4. 直接读取最新帧。

### 5.5 中心裁剪

`capture/crop.py` 提供：

1. `center_crop_frame()`：按中心裁剪。
2. `effective_crop_size()`：把裁剪宽高归一化到有效范围。

主循环在读到帧后会先做中心裁剪，再送给模型。

## 6. 视觉与推理

视觉相关代码在 `yolo_mouse_controller/vision/`。

### 6.1 模型信息读取

`vision/model_info.py` 负责模型元信息和固定输入尺寸：

1. `.onnx` 模型可从 metadata 里读取类别名。
2. `.engine` / `.trt` / `.plan` / `.rtr` 走 TensorRT 侧车文件或文件名推断。
3. `read_onnx_input_size()` 会读取 ONNX 输入 shape，判断固定输入尺寸。

这部分决定了 UI 中“读取类别”和“识别尺寸”的自动填充逻辑。

### 6.2 ONNX 推理器

`vision/detector.py` 是 ONNX Runtime 路径。它的流程是：

1. 读取模型输入尺寸。
2. 通过 `_add_gpu_dll_dirs()` 把 `torch/lib`、`tensorrt_libs`、`nvidia/cudnn/bin` 等目录加入 PATH / DLL 搜索路径。
3. 优先尝试 `CUDAExecutionProvider`，其次 `DmlExecutionProvider`，最后 `CPUExecutionProvider`。
4. 对输入帧做 letterbox、`cv2.dnn.blobFromImage()`、归一化。
5. 调用 `session.run()`。
6. 把输出交给 C++ NMS DLL 做后处理。

如果输入是 `tensor(float16)`，代码会把 blob 转成 `float16` 再送进 ONNX Runtime。

### 6.3 TensorRT 推理器

`vision/trt_detector.py` 是 TensorRT 路径，支持两套 API：

1. TensorRT 10 的 tensor API。
2. 旧版 binding API。

它的特点是：

1. 使用 `pycuda` 创建上下文。
2. 申请页锁定内存。
3. 异步 H2D / D2H 复制。
4. 通过 CUDA stream 同步。

TensorRT 路径同样复用 C++ NMS 解析输出。

### 6.4 C++ NMS DLL

`native_console/core/fast_nms.cpp` 提供 `run_yolov8_nms`，然后由 `detector.py` / `trt_detector.py` 通过 `ctypes` 调用。

它的算法流程是：

1. 遍历每个 anchor。
2. 在所有类别里找最大置信度类别。
3. 如果置信度超过阈值，就把 `cx, cy, w, h` 解码成 `x1, y1, x2, y2`。
4. 把候选框按置信度降序排序。
5. 做类内 NMS：只对同一类框计算 IoU 并抑制重叠。
6. 把结果写入预分配输出缓冲区。

输出格式固定为每个检测 6 个 float：

`x1, y1, x2, y2, conf, class_id`

## 7. 控制器与算法

控制逻辑主要在 `yolo_mouse_controller/control/`。

### 7.1 热键层

`control/hotkeys.py` 做两件事：

1. 用 `GetAsyncKeyState` 做按键边沿检测，避免短按漏检。
2. 用 `WH_MOUSE_LL` 低级鼠标钩子区分物理左键和注入事件。

这使得控制器能识别“玩家真的按了左键”，并在扳机逻辑里把人工操作优先级提高。

### 7.2 鼠标输出层

`control/mouse.py` 支持两个后端：

1. `sendinput`：直接走 Windows `SendInput`。
2. `lghub_siminput`：启动外部 Logitech siminput 工具，以 stream 方式持续发送指令。

它的实现重点是：

1. 对 LGHUB 后端维护 pending 位移。
2. 后台线程按固定间隔 flush。
3. 点击前先把 pending 位移清掉，避免位移和点击乱序。

### 7.3 目标选择与自瞄

`control/targeting.py` 是最核心的算法文件。它把“选谁”和“怎么移动”拆成两层。

#### 7.3.1 目标选择

`select()` 的逻辑是：

1. 先按类别名过滤。
2. 如果开启锁定目标，就优先尝试匹配上一帧锁定对象。
3. 锁定匹配优先走 IoU，失败再走中心距离和尺寸门限。
4. 最后按“靠近中心优先”或“高置信度优先”做排序。
5. 超过最大锁定距离的目标会被丢弃。

这部分的目的不是“找最显眼的框”，而是尽量稳定地跟住同一个目标，减少抖动切换。

#### 7.3.2 瞄准点计算

`_aim_point()` 会根据框和偏移量算出真正的瞄准点：

1. `aim_offset_x` 控制水平偏移。
2. `aim_offset_y` 可以被当前武器预设覆盖。
3. 0 到 1 的比例会被转换成相对框中心的偏移。

#### 7.3.3 自瞄算法

`aim()` 使用的是连续型控制思路，不是简单的“目标中心减准星中心”。它包含：

1. `Δt` 归一化，降低帧率波动对手感的影响。
2. Kalman 恒速预测，平滑目标位置并估计速度。
3. 未来点预测，用 `prediction_ms` 把目标外推到系统延迟后的时刻。
4. 动态死区，目标接近时直接归零，避免来回抖动。
5. 连续非线性增益，误差越大牵引越强，但不是线性暴力拉满。
6. 速度前馈，用目标速度补偿鼠标输出。
7. 压枪前馈，在开火状态下对 Y 轴做额外补偿。
8. 小数残差累积，避免整数步长截断损失精度。
9. 最大步长硬限幅，防止单帧输出过大。

这个算法的本质是：

`输出 = 速度前馈 + 未来误差牵引 + 压枪补偿 + 残差修正`

它不是纯粹的离散状态机，而是连续控制 + 工程限幅的组合。

### 7.4 扳机线程

`control/trigger.py` 是扳机控制器。每个预设一个独立工作线程，支持：

1. `hold`
2. `burst`
3. `semi`
4. `bolt`

它的关键设计是：

1. 主循环只负责喂状态，不阻塞。
2. 实际点击、按住、冷却都在工作线程里完成。
3. 如果检测到玩家物理左键接管，会优先让出控制权，避免把人工开火打断。

### 7.5 主循环

`yolo_mouse_controller/app.py` 把所有部件串起来。主循环顺序是：

1. 读帧。
2. 裁剪。
3. 推理。
4. 目标选择。
5. 计算鼠标步长。
6. 输出鼠标移动。
7. 更新扳机状态。
8. 画预览。
9. 输出指标。

`app.py` 还维护了：

1. FPS 统计。
2. 运行日志异步打印队列。
3. 武器切换状态。
4. `MOUSE_STATUS`、`MOUSE_CMD`、`AIM_PROFILE`、`WEAPON_SWITCH` 等日志格式。

## 8. Web 控制台

前端在 `web_console/`。

### 8.1 页面结构

`web_console/index.html` 是一个单页控制面板，分为：

1. 总览。
2. 采集。
3. 模型。
4. 鼠标。
5. 日志。

页面顶部还有实时指标条，显示：

1. 截图延时。
2. 推理延时。
3. 端到端延时。
4. 总帧率。

### 8.2 前端逻辑

`web_console/app.js` 负责：

1. 读取并渲染默认配置。
2. 拉取 `/api/config`。
3. 保存配置。
4. 启动和停止控制器。
5. 浏览模型。
6. 读取模型类别。
7. 扫描设备。
8. 触发鼠标测试。
9. 轮询 `/api/status`，刷新日志和指标。

前端还会解析控制器日志中的运行事件，例如：

1. `MOUSE_STATUS`
2. `MOUSE_CMD`
3. `AIM_PROFILE`
4. `WEAPON_SWITCH`

### 8.3 样式

`web_console/styles.css` 定义了页面布局和视觉风格：

1. 左侧导航栏。
2. 中央工作区。
3. 指标卡片。
4. 面板卡片。
5. 统一的按钮和输入控件样式。

### 8.4 控制台宿主

`native_console/server.cpp` 同时充当：

1. 静态资源服务器。
2. 本地 API 服务。
3. Python 子进程宿主。
4. 日志收集器。
5. 指标解析器。

它会把 Python 控制器的 stdout/stderr 读出来，解析出 `METRICS` 行中的：

1. `capture_ms`
2. `inference_ms`
3. `total_ms`
4. `fps`

它还负责：

1. 配置落盘到 `.runtime/web-console-config.json`。
2. 模型浏览。
3. 模型信息读取。
4. 设备扫描。
5. 鼠标测试调用。
6. 启动和停止 Python 控制器。

服务器启动时会注入 cuDNN 路径，目的是让 GPU 版 ONNX Runtime 能找到对应 DLL。

## 9. 测试与验证

测试目录在 `tests/`。

### 9.1 裁剪测试

`tests/test_crop.py` 主要验证中心裁剪和有效尺寸归一化。

### 9.2 模型信息测试

`tests/test_model_info.py` 验证输入尺寸读取和类别读取。

### 9.3 目标与步长测试

`tests/test_targeting.py` 验证：

1. 最近合法目标选择。
2. 死区行为。
3. direct / stepped 等移动模式的步长输出。
4. 置信度优先的选择策略。

注意：测试文件里有些旧名字看起来是历史 API 的残留，实际代码已经演进到 `ElegantAimController` 这一套实现。

## 10. 关键算法总结

### 10.1 目标选择算法

目标选择不是简单取最高置信度框，而是结合了：

1. 类别过滤。
2. 锁定目标复用。
3. IoU 匹配。
4. 距离门限。
5. 尺寸相似性判断。
6. 中心优先 / 置信度优先排序。

### 10.2 自瞄控制算法

`ElegantAimController` 的核心思想是：

1. 先用 Kalman 平滑位置并估计速度（支持高精度 `Δt` 归一化）。
2. 再把速度和未来误差结合（绝对时间落点预测）。
3. 用连续增益函数控制强度。
4. 用死区和残差避免抖动。
5. 用压枪前馈和残差解决实际游戏中的连续开火偏移。

### 10.3 扳机算法

扳机不是单个 if 语句，而是独立线程状态机：

1. `hold`：持续按住。
2. `burst`：连点固定次数。
3. `semi`：触发一次后等待目标离开。
4. `bolt`：触发一次后进入冷却。

### 10.4 NMS 算法

C++ NMS 的思路是先按每个 anchor 选出最强类别，再做排序和类内抑制。它适合把 Python 层后处理的开销压到很低。
*注：DLL 与 Python 连接处已引入 `max_out` 长度与 Null 指针的安全截断，并在 Python 层强制使用 `np.ascontiguousarray(dtype=np.float32)`，防止在高速推断环境下的指针越界与意外断异常崩溃。*

### 10.5 跨端 IPC 通信升级 (v2)

在 v2 版本中，用于将推理与采集核心 Metrics 向前端展示的通道，从原始的“基于解析 stdout 输出的正则表达式拦截”改为了 UDP (`127.0.0.1:8766`) 异步投递。
利用无连接、非阻塞的 Sockets，Python 端主循环可以极低延迟无卡顿地将 `capture_ms` 等核心指标甩向 C++ 宿主侧驻留的后台读取线程。这彻底斩断了标准输出流容易积压导致的整个流水线拖滞问题。

## 11. 脚本用途归档

1. `scripts/run.ps1`：启动 Python 控制器。
2. `scripts/build-web-console.ps1`：构建 Web 控制台宿主。
3. `scripts/model_info_cli.py`：读取模型信息。
4. `scripts/device_info_cli.py`：读取推理设备。
5. `scripts/mouse_test_cli.py`：鼠标测试和屏幕覆盖层演示。
6. `scripts/benchmark_models.py`：模型基准测试。
7. `scripts/console.py`：桌面控制台入口。

## 12. 运行时依赖关系

项目依赖可以理解成三层：

1. Python 业务层：`numpy`、`opencv-python`、`pyyaml`、`ultralytics`、`onnxruntime`。
2. GPU / 推理层：`onnxruntime-gpu` 或 `onnxruntime-directml`、`pycuda`、TensorRT 绑定。
3. 本地服务层：`native_console/server.cpp` + Windows API + Winsock。

## 13. 维护重点

后续维护时最值得盯住的地方是：

1. 采集延迟：`capture_ms`。
2. 推理延迟：`inference_ms`。
3. 端到端延迟：`total_ms`。
4. 目标选择稳定性：锁定、IoU、类别过滤。
5. 鼠标后端兼容性：SendInput / LGHUB。
6. Web 控制台与 Python 配置字段是否同步。
7. ONNX / TensorRT 的输入输出 shape 是否仍然匹配 C++ NMS。

## 14. 一句话总览

这是一个“本地 Web 控制台 + C++ 宿主 + Python 推理控制器 + 视觉采集 + 连续控制算法 + 鼠标后端”的 Windows YOLO 鼠标控制系统；它的核心不是单一模型，而是采集、推理、目标选择、步长控制和输入输出后端的整条链路设计。
