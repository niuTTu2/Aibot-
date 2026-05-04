#!/usr/bin/env python3
"""
对比 TensorRT 和 ONNX 模型的推理性能

用法：
    python scripts/benchmark_models.py
"""

import time
import numpy as np
from pathlib import Path

# TensorRT 模型路径
TRT_MODEL = Path(r"D:\trt_models\xiaohuamaoV8_640_fp16.trt")
ONNX_MODEL = Path(r"D:\trt_models\xiaohuamaoV8_640_fp16.onnx")

# 测试参数
WARMUP_RUNS = 10
BENCHMARK_RUNS = 100
INPUT_SIZE = 640


def benchmark_trt():
    """测试 TensorRT 模型"""
    print("\n" + "="*60)
    print("测试 TensorRT 模型")
    print("="*60)

    try:
        import tensorrt as trt
        import pycuda.autoinit
        import pycuda.driver as cuda
    except ImportError as e:
        print(f"❌ TensorRT 未安装: {e}")
        return None

    if not TRT_MODEL.exists():
        print(f"❌ 模型文件不存在: {TRT_MODEL}")
        return None

    # 加载引擎
    logger = trt.Logger(trt.Logger.WARNING)
    runtime = trt.Runtime(logger)

    print(f"📂 加载模型: {TRT_MODEL}")
    with open(TRT_MODEL, "rb") as f:
        engine = runtime.deserialize_cuda_engine(f.read())

    if engine is None:
        print("❌ 引擎加载失败")
        return None

    context = engine.create_execution_context()

    # 获取输入输出信息
    input_name = engine.get_tensor_name(0)
    output_name = engine.get_tensor_name(1)
    input_shape = tuple(engine.get_tensor_shape(input_name))
    output_shape = tuple(engine.get_tensor_shape(output_name))

    print(f"✓ 输入: {input_name} {input_shape}")
    print(f"✓ 输出: {output_name} {output_shape}")

    # 分配内存
    input_data = np.random.rand(*input_shape).astype(np.float32)
    output_data = np.zeros(output_shape, dtype=np.float32)

    d_input = cuda.mem_alloc(input_data.nbytes)
    d_output = cuda.mem_alloc(output_data.nbytes)

    stream = cuda.Stream()

    # Warmup
    print(f"🔥 预热 {WARMUP_RUNS} 次...")
    for _ in range(WARMUP_RUNS):
        cuda.memcpy_htod_async(d_input, input_data, stream)
        context.set_tensor_address(input_name, int(d_input))
        context.set_tensor_address(output_name, int(d_output))
        context.execute_async_v3(stream.handle)
        cuda.memcpy_dtoh_async(output_data, d_output, stream)
        stream.synchronize()

    # Benchmark
    print(f"⚡ 基准测试 {BENCHMARK_RUNS} 次...")
    times = []
    for _ in range(BENCHMARK_RUNS):
        start = time.perf_counter()

        cuda.memcpy_htod_async(d_input, input_data, stream)
        context.set_tensor_address(input_name, int(d_input))
        context.set_tensor_address(output_name, int(d_output))
        context.execute_async_v3(stream.handle)
        cuda.memcpy_dtoh_async(output_data, d_output, stream)
        stream.synchronize()

        end = time.perf_counter()
        times.append((end - start) * 1000)

    avg_time = np.mean(times)
    min_time = np.min(times)
    max_time = np.max(times)
    std_time = np.std(times)

    print(f"\n📊 TensorRT 性能:")
    print(f"  平均: {avg_time:.2f} ms")
    print(f"  最小: {min_time:.2f} ms")
    print(f"  最大: {max_time:.2f} ms")
    print(f"  标准差: {std_time:.2f} ms")
    print(f"  FPS: {1000/avg_time:.1f}")

    return avg_time


def benchmark_onnx():
    """测试 ONNX 模型"""
    print("\n" + "="*60)
    print("测试 ONNX 模型")
    print("="*60)

    try:
        import onnxruntime as ort
    except ImportError as e:
        print(f"❌ ONNX Runtime 未安装: {e}")
        return None

    if not ONNX_MODEL.exists():
        print(f"❌ 模型文件不存在: {ONNX_MODEL}")
        return None

    # 加载模型
    print(f"📂 加载模型: {ONNX_MODEL}")

    providers = ort.get_available_providers()
    print(f"✓ 可用 Providers: {providers}")

    # 优先使用 TensorRT EP
    if 'TensorrtExecutionProvider' in providers:
        print("✓ 使用 TensorrtExecutionProvider")
        session = ort.InferenceSession(str(ONNX_MODEL), providers=['TensorrtExecutionProvider'])
    elif 'CUDAExecutionProvider' in providers:
        print("✓ 使用 CUDAExecutionProvider")
        session = ort.InferenceSession(str(ONNX_MODEL), providers=['CUDAExecutionProvider'])
    else:
        print("⚠ 使用 CPUExecutionProvider")
        session = ort.InferenceSession(str(ONNX_MODEL), providers=['CPUExecutionProvider'])

    # 获取输入输出信息
    input_name = session.get_inputs()[0].name
    input_shape = session.get_inputs()[0].shape
    output_name = session.get_outputs()[0].name
    output_shape = session.get_outputs()[0].shape

    print(f"✓ 输入: {input_name} {input_shape}")
    print(f"✓ 输出: {output_name} {output_shape}")

    # 准备输入
    input_data = np.random.rand(1, 3, INPUT_SIZE, INPUT_SIZE).astype(np.float32)

    # Warmup
    print(f"🔥 预热 {WARMUP_RUNS} 次...")
    for _ in range(WARMUP_RUNS):
        session.run([output_name], {input_name: input_data})

    # Benchmark
    print(f"⚡ 基准测试 {BENCHMARK_RUNS} 次...")
    times = []
    for _ in range(BENCHMARK_RUNS):
        start = time.perf_counter()
        session.run([output_name], {input_name: input_data})
        end = time.perf_counter()
        times.append((end - start) * 1000)

    avg_time = np.mean(times)
    min_time = np.min(times)
    max_time = np.max(times)
    std_time = np.std(times)

    print(f"\n📊 ONNX Runtime 性能:")
    print(f"  平均: {avg_time:.2f} ms")
    print(f"  最小: {min_time:.2f} ms")
    print(f"  最大: {max_time:.2f} ms")
    print(f"  标准差: {std_time:.2f} ms")
    print(f"  FPS: {1000/avg_time:.1f}")

    return avg_time


def main():
    print("🚀 YOLO 模型性能基准测试")
    print(f"输入尺寸: {INPUT_SIZE}x{INPUT_SIZE}")
    print(f"预热次数: {WARMUP_RUNS}")
    print(f"测试次数: {BENCHMARK_RUNS}")

    trt_time = benchmark_trt()
    onnx_time = benchmark_onnx()

    print("\n" + "="*60)
    print("📊 对比结果")
    print("="*60)

    if trt_time and onnx_time:
        speedup = onnx_time / trt_time
        print(f"TensorRT:     {trt_time:.2f} ms")
        print(f"ONNX Runtime: {onnx_time:.2f} ms")
        print(f"加速比:       {speedup:.2f}x")

        if speedup < 1.1:
            print("\n⚠️  警告：TensorRT 没有明显加速！")
            print("可能原因：")
            print("  1. ONNX Runtime 使用了 TensorRT EP（已经很快了）")
            print("  2. TensorRT 引擎未针对当前 GPU 优化")
            print("  3. 模型太小，瓶颈不在推理")
    elif trt_time:
        print(f"TensorRT:     {trt_time:.2f} ms")
        print("ONNX Runtime: 未测试")
    elif onnx_time:
        print("TensorRT:     未测试")
        print(f"ONNX Runtime: {onnx_time:.2f} ms")
    else:
        print("❌ 两个模型都无法测试")


if __name__ == "__main__":
    main()
