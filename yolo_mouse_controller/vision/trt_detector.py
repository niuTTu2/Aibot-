from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from yolo_mouse_controller.config import ModelConfig
from yolo_mouse_controller.vision.detector import Detection, _add_gpu_dll_dirs, _fast_nms
from yolo_mouse_controller.vision.model_info import normalize_imgsz, read_trt_sidecar_classes


class TrtDetector:
    """TensorRT engine inference for YOLOv8.

    Supports TensorRT 10's tensor API and older binding API. Expected output is
    either raw YOLOv8 [1, 84, 8400]-style predictions or post-NMS [1, N, 6].
    """

    def __init__(self, config: ModelConfig) -> None:
        _add_gpu_dll_dirs()
        try:
            import tensorrt as trt
            import pycuda.autoinit  # noqa: F401  # creates CUDA context
            import pycuda.driver as cuda
        except ImportError as e:
            raise ImportError(
                "TensorRT backend requires TensorRT runtime libraries and pycuda.\n"
                "Install/check with:\n"
                "  python -m pip install tensorrt-cu12-bindings tensorrt-cu12-libs pycuda\n"
                f"Original error: {e}"
            ) from e

        self.config = config
        self._trt = trt
        self._cuda = cuda
        self._trt10_api = False

        logger = trt.Logger(trt.Logger.WARNING)
        runtime = trt.Runtime(logger)
        print(f"Loading TensorRT engine: {config.path}")
        with open(config.path, "rb") as f:
            self.engine = runtime.deserialize_cuda_engine(f.read())
        if self.engine is None:
            raise RuntimeError(
                f"TensorRT failed to deserialize engine: {config.path}. "
                "Engine files are not portable across TensorRT major versions/GPU targets; rebuild it locally."
            )
        self.context = self.engine.create_execution_context()

        self._setup_bindings()
        self.names: dict[int, str] = self._load_names(Path(config.path))

        self._max_out = 300
        self._out_buffer = np.zeros(self._max_out * 6, dtype=np.float32)

    # ------------------------------------------------------------------

    def _setup_bindings(self) -> None:
        trt = self._trt
        cuda = self._cuda

        self._input_idx = -1
        self._output_idx = -1
        self._input_name: str | None = None
        self._output_name: str | None = None
        self._trt10_api = hasattr(self.engine, "num_io_tensors")

        if self._trt10_api:
            for i in range(self.engine.num_io_tensors):
                name = self.engine.get_tensor_name(i)
                shape = tuple(self.engine.get_tensor_shape(name))
                dtype = trt.nptype(self.engine.get_tensor_dtype(name))
                is_input = self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT
                print(f"  TRT tensor[{i}] '{name}' shape={shape} dtype={dtype.__name__} input={is_input}")
                if is_input and self._input_name is None:
                    self._input_idx = i
                    self._input_name = name
                    self._input_shape = shape
                    self._input_dtype = dtype
                elif not is_input and self._output_name is None:
                    self._output_idx = i
                    self._output_name = name
                    self._output_shape = shape
                    self._output_dtype = dtype
        else:
            for i in range(self.engine.num_bindings):
                name = self.engine.get_binding_name(i)
                shape = tuple(self.engine.get_binding_shape(i))
                dtype = trt.nptype(self.engine.get_binding_dtype(i))
                is_input = self.engine.binding_is_input(i)
                print(f"  TRT binding[{i}] '{name}' shape={shape} dtype={dtype.__name__} input={is_input}")
                if is_input and self._input_idx == -1:
                    self._input_idx = i
                    self._input_name = name
                    self._input_shape = shape
                    self._input_dtype = dtype
                elif not is_input and self._output_idx == -1:
                    self._output_idx = i
                    self._output_name = name
                    self._output_shape = shape
                    self._output_dtype = dtype

        if self._input_idx == -1 or self._output_idx == -1:
            raise RuntimeError("TRT engine: could not identify input/output tensors")
        if any(int(dim) < 0 for dim in (*self._input_shape, *self._output_shape)):
            raise RuntimeError(
                "TRT engine has dynamic shapes. Rebuild with a fixed input size, "
                "or extend TrtDetector to call context.set_input_shape()."
            )

        _, _, h, w = self._input_shape
        self.imgsz = normalize_imgsz((w, h))

        in_elems = int(np.prod(self._input_shape))
        out_elems = int(np.prod(self._output_shape))

        self._h_input = cuda.pagelocked_empty(in_elems, dtype=self._input_dtype)
        self._h_output = cuda.pagelocked_empty(out_elems, dtype=self._output_dtype)
        self._d_input = cuda.mem_alloc(self._h_input.nbytes)
        self._d_output = cuda.mem_alloc(self._h_output.nbytes)
        self._stream = cuda.Stream()

    def _load_names(self, engine_path: Path) -> dict[int, str]:
        """Load class names from sidecar files or same-name ONNX metadata."""
        return dict(read_trt_sidecar_classes(engine_path))

    # ------------------------------------------------------------------

    def detect(self, img: np.ndarray) -> list[Detection]:
        cuda = self._cuda
        original_h, original_w = img.shape[:2]

        imgsz_w, imgsz_h = (
            (self.imgsz, self.imgsz) if isinstance(self.imgsz, int)
            else (self.imgsz[0], self.imgsz[1])
        )

        r = min(imgsz_w / original_w, imgsz_h / original_h)
        new_w = int(round(original_w * r))
        new_h = int(round(original_h * r))
        dw = (imgsz_w - new_w) / 2
        dh = (imgsz_h - new_h) / 2

        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        top = int(round(dh - 0.1))
        bottom = int(round(dh + 0.1))
        left = int(round(dw - 0.1))
        right = int(round(dw + 0.1))
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )

        blob = cv2.dnn.blobFromImage(padded, 1.0 / 255.0, swapRB=True)
        if self._input_dtype == np.float16:
            blob = blob.astype(np.float16)

        np.copyto(self._h_input, blob.ravel())
        cuda.memcpy_htod_async(self._d_input, self._h_input, self._stream)

        if self._trt10_api:
            assert self._input_name is not None and self._output_name is not None
            self.context.set_tensor_address(self._input_name, int(self._d_input))
            self.context.set_tensor_address(self._output_name, int(self._d_output))
            self.context.execute_async_v3(stream_handle=self._stream.handle)
        else:
            bindings = [None] * self.engine.num_bindings
            bindings[self._input_idx] = int(self._d_input)
            bindings[self._output_idx] = int(self._d_output)
            self.context.execute_async_v2(bindings=bindings, stream_handle=self._stream.handle)

        cuda.memcpy_dtoh_async(self._h_output, self._d_output, self._stream)
        self._stream.synchronize()

        preds = self._h_output.reshape(self._output_shape)
        return self._parse(preds, r, dw, dh)

    def _parse(self, preds: np.ndarray, r: float, dw: float, dh: float) -> list[Detection]:
        preds = preds[0]

        if preds.ndim == 2 and preds.shape[1] == 6:
            detections = []
            for row in preds:
                x1, y1, x2, y2, conf, cls_id = row
                if conf < self.config.conf:
                    continue
                x1 = (x1 - dw) / r
                y1 = (y1 - dh) / r
                x2 = (x2 - dw) / r
                y2 = (y2 - dh) / r
                detections.append(Detection(
                    xyxy=(float(x1), float(y1), float(x2), float(y2)),
                    confidence=float(conf),
                    class_id=int(cls_id),
                    class_name=str(self.names.get(int(cls_id), int(cls_id))),
                ))
            return detections

        if preds.ndim == 2 and preds.shape[0] >= 4:
            num_classes = preds.shape[0] - 4
            num_anchors = preds.shape[1]

            if _fast_nms is not None:
                import ctypes
                preds_f32 = np.ascontiguousarray(preds, dtype=np.float32)
                out_c = self._out_buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
                preds_c = preds_f32.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
                num_det = _fast_nms.run_yolov8_nms(
                    preds_c, num_classes, num_anchors,
                    float(self.config.conf), float(self.config.iou),
                    out_c, ctypes.c_int(self._max_out),
                )
                # Safely clamp num_det
                num_det = min(num_det, self._max_out)
                detections = []
                for i in range(num_det):
                    idx = i * 6
                    x1, y1, x2, y2, conf, cls_id = self._out_buffer[idx:idx + 6]
                    x1 = (x1 - dw) / r
                    y1 = (y1 - dh) / r
                    x2 = (x2 - dw) / r
                    y2 = (y2 - dh) / r
                    detections.append(Detection(
                        xyxy=(float(x1), float(y1), float(x2), float(y2)),
                        confidence=float(conf),
                        class_id=int(cls_id),
                        class_name=str(self.names.get(int(cls_id), int(cls_id))),
                    ))
                return detections

        return []
