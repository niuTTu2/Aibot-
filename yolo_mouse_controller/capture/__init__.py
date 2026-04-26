from .base import FrameSource
from .crop import center_crop_frame, effective_crop_size

__all__ = ["FrameSource", "center_crop_frame", "create_frame_source", "effective_crop_size"]


def create_frame_source(*args, **kwargs):
    from .factory import create_frame_source as _create_frame_source

    return _create_frame_source(*args, **kwargs)
