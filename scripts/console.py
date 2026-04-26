from __future__ import annotations

import sys
from pathlib import Path


project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from yolo_mouse_controller.gui import main


if __name__ == "__main__":
    main()
