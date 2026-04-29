from .detector import Detection, YoloDetector
from .model_info import ModelInfo, read_model_info

__all__ = ["Detection", "ModelInfo", "TrtDetector", "YoloDetector", "read_model_info"]


def __getattr__(name: str):
    if name == "TrtDetector":
        from .trt_detector import TrtDetector
        return TrtDetector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
