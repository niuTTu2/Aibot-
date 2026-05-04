from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _resolve_model_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read model classes and input size")
    parser.add_argument("model", nargs="?", help="Model path")
    parser.add_argument("--model", dest="model_opt", help="Model path")
    parser.add_argument("--path", dest="path_opt", help="Model path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_model = args.model_opt or args.path_opt or args.model
    if not raw_model:
        print(json.dumps({"ok": False, "error": "model path is required"}, ensure_ascii=False))
        return 2

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from yolo_mouse_controller.vision.model_info import format_imgsz, read_model_info

    model_path = _resolve_model_path(raw_model)
    if not model_path.exists():
        print(
            json.dumps(
                {"ok": False, "error": f"model not found: {model_path}"},
                ensure_ascii=False,
            )
        )
        return 1

    try:
        info = read_model_info(model_path)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    payload = {
        "ok": True,
        "path": str(model_path),
        "classes": [{"id": int(cid), "name": str(name)} for cid, name in info.classes],
        "class_count": len(info.classes),
        "fixed_imgsz": info.fixed_imgsz,
        "fixed_imgsz_text": format_imgsz(info.fixed_imgsz) if info.fixed_imgsz is not None else None,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
