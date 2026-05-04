import time, cv2, numpy as np; from yolo_mouse_controller.config import ModelConfig; from yolo_mouse_controller.vision.detector import YoloDetector; img=np.zeros((1080,1920,3), dtype=np.uint8); y=YoloDetector(ModelConfig(path='models/sample/yolov8n.onnx', device='0', imgsz=640)); t0=time.time(); y.detect(img); import cProfile; cProfile.run('for _ in range(50): y.detect(img)', sort='cumtime')

