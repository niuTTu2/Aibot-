from __future__ import annotations

import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from yolo_mouse_controller.vision.model_info import read_model_info


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "model path required"}))
        return 2

    try:
        noise = StringIO()
        with redirect_stdout(noise), redirect_stderr(noise):
            info = read_model_info(sys.argv[1])
        fixed = info.fixed_imgsz
        if isinstance(fixed, tuple):
            fixed_value: int | list[int] | None = [fixed[0], fixed[1]]
        else:
            fixed_value = fixed
        print(
            json.dumps(
                {
                    "ok": True,
                    "classes": [{"id": class_id, "name": name} for class_id, name in info.classes],
                    "fixed_imgsz": fixed_value,
                },
                ensure_ascii=True,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
