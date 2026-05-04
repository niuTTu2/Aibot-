# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['yolo_mouse_controller\\__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('web_console', 'web_console'),
        ('configs/config.example.yaml', 'configs'),
        ('models/sample/yolov8n.onnx', 'models/sample'),
        ('models/sample/yolov8n.pt', 'models/sample'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YoloMouseController',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
