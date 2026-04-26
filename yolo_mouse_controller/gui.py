from __future__ import annotations

import json
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, Tk, filedialog, messagebox
from tkinter import scrolledtext, ttk

from yolo_mouse_controller.vision.model_info import ModelInfo, format_imgsz, read_model_info


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
GENERATED_CONFIG = RUNTIME_DIR / "console-config.json"

BG = "#eef2f6"
PANEL = "#ffffff"
SIDEBAR = "#162033"
SIDEBAR_SOFT = "#22304a"
TEXT = "#172033"
MUTED = "#667085"
ACCENT = "#2563eb"
SUCCESS = "#16a34a"
DANGER = "#dc2626"


class ControlConsole:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("YOLO 鼠标控制台")
        self.root.geometry("1180x760")
        self.root.minsize(1040, 680)
        self.root.configure(bg=BG)

        self.process: subprocess.Popen[str] | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.source = StringVar(value="dxgi")
        self.monitor_index = IntVar(value=0)
        self.device_index = IntVar(value=0)
        self.width = IntVar(value=1920)
        self.height = IntVar(value=1080)
        self.crop_width = IntVar(value=0)
        self.crop_height = IntVar(value=0)
        self.fps = IntVar(value=60)

        self.model_path = StringVar(value="yolov8n.pt")
        self.imgsz = IntVar(value=640)
        self.conf = DoubleVar(value=0.35)
        self.iou = DoubleVar(value=0.45)
        self.device = StringVar(value="")

        self.class_names = StringVar(value="")
        self.model_classes: list[tuple[int, str]] = []
        self.selected_class_ids: set[int] = set()
        self.class_status = StringVar(value="未读取类别；空选表示不过滤")
        self.loading_model_info = False
        self._updating_class_list = False
        self.prefer_center = BooleanVar(value=True)
        self.aim_offset_x = DoubleVar(value=0.0)
        self.aim_offset_y = DoubleVar(value=0.0)
        self.max_distance_px = IntVar(value=900)

        self.mouse_enabled = BooleanVar(value=True)
        self.hold_to_move = BooleanVar(value=True)
        self.enable_key = StringVar(value="0x06")
        self.sensitivity = DoubleVar(value=0.35)
        self.smoothing = DoubleVar(value=0.55)
        self.deadzone_px = IntVar(value=3)
        self.max_step_px = IntVar(value=45)
        self.click_enabled = BooleanVar(value=False)
        self.click_key = StringVar(value="0x05")

        self.preview = BooleanVar(value=True)
        self.preview_scale = DoubleVar(value=0.5)
        self.print_fps = BooleanVar(value=True)
        self.status = StringVar(value="未启动")
        self.metric_inference = StringVar(value="-- ms")
        self.metric_total = StringVar(value="-- ms")
        self.metric_fps = StringVar(value="-- FPS")

        self._setup_style()
        self._build_ui()
        self._poll_logs()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_style(self) -> None:
        self.style = ttk.Style(self.root)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.style.configure(".", font=("Microsoft YaHei UI", 10), background=BG, foreground=TEXT)
        self.style.configure("Root.TFrame", background=BG)
        self.style.configure("Card.TFrame", background=PANEL, relief="flat")
        self.style.configure("Sidebar.TFrame", background=SIDEBAR)
        self.style.configure("SidebarSoft.TFrame", background=SIDEBAR_SOFT)
        self.style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Microsoft YaHei UI", 20, "bold"))
        self.style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 10))
        self.style.configure("CardTitle.TLabel", background=PANEL, foreground=TEXT, font=("Microsoft YaHei UI", 12, "bold"))
        self.style.configure("CardHint.TLabel", background=PANEL, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        self.style.configure("Field.TLabel", background=PANEL, foreground="#344054")
        self.style.configure("SideTitle.TLabel", background=SIDEBAR, foreground="#f8fafc", font=("Microsoft YaHei UI", 16, "bold"))
        self.style.configure("SideText.TLabel", background=SIDEBAR, foreground="#cbd5e1")
        self.style.configure("Status.TLabel", background=SIDEBAR_SOFT, foreground="#dbeafe", padding=(12, 8))
        self.style.configure("Primary.TButton", padding=(18, 10), font=("Microsoft YaHei UI", 10, "bold"))
        self.style.configure("Danger.TButton", padding=(18, 10))
        self.style.configure("Tool.TButton", padding=(12, 8))
        self.style.configure("TButton", padding=(10, 7))
        self.style.configure("TEntry", fieldbackground="#ffffff", bordercolor="#cbd5e1", lightcolor="#cbd5e1", padding=6)
        self.style.configure("TCombobox", fieldbackground="#ffffff", bordercolor="#cbd5e1", padding=6)
        self.style.configure("TSpinbox", fieldbackground="#ffffff", bordercolor="#cbd5e1", padding=6)
        self.style.configure("TNotebook", background=BG, borderwidth=0)
        self.style.configure("TNotebook.Tab", padding=(18, 10), font=("Microsoft YaHei UI", 10, "bold"))

    def _build_ui(self) -> None:
        root = ttk.Frame(self.root, style="Root.TFrame", padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(root, style="Sidebar.TFrame", padding=20)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        sidebar.configure(width=280)
        sidebar.grid_propagate(False)
        self._build_sidebar(sidebar)

        main = ttk.Frame(root, style="Root.TFrame")
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)
        self._build_main(main)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="YOLO 鼠标控制台", style="SideTitle.TLabel").pack(anchor="w")
        ttk.Label(parent, text="视觉识别、目标选择、鼠标输出", style="SideText.TLabel").pack(anchor="w", pady=(8, 24))

        status_card = ttk.Frame(parent, style="SidebarSoft.TFrame", padding=14)
        status_card.pack(fill="x", pady=(0, 16))
        ttk.Label(status_card, text="当前状态", style="Status.TLabel").pack(fill="x")
        ttk.Label(status_card, textvariable=self.status, style="Status.TLabel", font=("Microsoft YaHei UI", 14, "bold")).pack(
            fill="x", pady=(8, 0)
        )

        metrics_card = ttk.Frame(parent, style="SidebarSoft.TFrame", padding=14)
        metrics_card.pack(fill="x", pady=(0, 16))
        ttk.Label(metrics_card, text="运行指标", style="Status.TLabel").pack(fill="x")
        self._metric_row(metrics_card, "推理延时", self.metric_inference)
        self._metric_row(metrics_card, "端到端延时", self.metric_total)
        self._metric_row(metrics_card, "总帧率", self.metric_fps)

        ttk.Button(parent, text="启动控制器", style="Primary.TButton", command=self.start_controller).pack(fill="x", pady=(0, 10))
        ttk.Button(parent, text="停止控制器", style="Danger.TButton", command=self.stop_controller).pack(fill="x", pady=(0, 10))
        ttk.Button(parent, text="保存当前配置", style="Tool.TButton", command=self.save_config).pack(fill="x", pady=(8, 0))
        ttk.Button(parent, text="安装/修复依赖", style="Tool.TButton", command=self.install_dependencies).pack(fill="x", pady=(10, 0))

        tips = ttk.Frame(parent, style="Sidebar.TFrame")
        tips.pack(fill="both", expand=True, pady=(28, 0))
        ttk.Label(tips, text="安全提示", style="SideText.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            tips,
            text="建议先开启预览并关闭点击。\n确认目标稳定后，再调高灵敏度或启用点击。",
            style="SideText.TLabel",
            wraplength=230,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _metric_row(self, parent: ttk.Frame, label: str, variable: StringVar) -> None:
        row = ttk.Frame(parent, style="SidebarSoft.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text=label, style="Status.TLabel").pack(side="left")
        ttk.Label(row, textvariable=variable, style="Status.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(side="right")

    def _build_main(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="Root.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="控制面板", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="调整参数后点击启动，日志会在底部实时显示。", style="Subtitle.TLabel").grid(row=1, column=0, sticky="w")

        body = ttk.Frame(parent, style="Root.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=2)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        notebook = ttk.Notebook(body)
        notebook.grid(row=0, column=0, sticky="nsew")

        capture_tab = ttk.Frame(notebook, style="Root.TFrame", padding=12)
        model_tab = ttk.Frame(notebook, style="Root.TFrame", padding=12)
        mouse_tab = ttk.Frame(notebook, style="Root.TFrame", padding=12)
        notebook.add(capture_tab, text="画面采集")
        notebook.add(model_tab, text="识别目标")
        notebook.add(mouse_tab, text="鼠标控制")

        self._build_capture_tab(capture_tab)
        self._build_model_tab(model_tab)
        self._build_mouse_tab(mouse_tab)

        log_card = self._card(body, "运行日志", "启动、依赖安装、YOLO 推理状态都会显示在这里。")
        log_card.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        log_card.rowconfigure(1, weight=1)
        log_card.columnconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            log_card,
            height=10,
            wrap="word",
            state="disabled",
            bg="#0f172a",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            relief="flat",
            font=("Cascadia Mono", 10),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

    def _build_capture_tab(self, parent: ttk.Frame) -> None:
        grid = self._card(parent, "输入源", "DXGI 用于本机画面，采集卡用于 HDMI 或摄像头输入。")
        grid.pack(fill="both", expand=True)
        self._combo(grid, "输入来源", self.source, ["dxgi", "capture_card"], 1)
        self._spin(grid, "DXGI 显示器编号", self.monitor_index, 0, 8, 2)
        self._spin(grid, "采集卡设备号", self.device_index, 0, 16, 3)
        self._spin(grid, "宽度", self.width, 320, 7680, 4)
        self._spin(grid, "高度", self.height, 240, 4320, 5)
        self._spin(grid, "中心裁剪宽度", self.crop_width, 0, 7680, 6)
        self._spin(grid, "中心裁剪高度", self.crop_height, 0, 4320, 7)
        self._spin(grid, "帧率", self.fps, 1, 240, 8)
        self._check(grid, "显示预览窗口", self.preview, 9)
        self._scale(grid, "预览缩放", self.preview_scale, 0.1, 1.0, 10)
        self._check(grid, "打印指标日志", self.print_fps, 11)

    def _build_model_tab(self, parent: ttk.Frame) -> None:
        grid = self._card(parent, "YOLO 模型", "选择权重并设置筛选规则。空类别表示不过滤。")
        grid.pack(fill="both", expand=True)
        ttk.Label(grid, text="模型路径", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=7)
        path_row = ttk.Frame(grid, style="Card.TFrame")
        path_row.grid(row=1, column=1, sticky="ew", pady=7)
        ttk.Entry(path_row, textvariable=self.model_path).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="浏览", command=self.browse_model).pack(side="left", padx=(8, 0))
        self._spin(grid, "推理尺寸", self.imgsz, 160, 2048, 2)
        self._scale(grid, "置信度", self.conf, 0.05, 0.95, 3)
        self._scale(grid, "IOU", self.iou, 0.05, 0.95, 4)
        self._entry(grid, "设备", self.device, 5, "空=自动，0=第一张显卡，cpu=CPU")
        self._class_selector(grid, 6)
        self._check(grid, "优先选择画面中心附近目标", self.prefer_center, 8)
        self._scale(grid, "水平偏移", self.aim_offset_x, -1.0, 1.0, 9)
        self._scale(grid, "垂直偏移", self.aim_offset_y, -1.0, 1.0, 10)
        self._spin(grid, "最大锁定距离", self.max_distance_px, 10, 4000, 11)

    def _build_mouse_tab(self, parent: ttk.Frame) -> None:
        grid = self._card(parent, "鼠标输出", "默认按住鼠标侧键 XBUTTON2 才移动，点击功能默认关闭。")
        grid.pack(fill="both", expand=True)
        self._check(grid, "启用鼠标移动", self.mouse_enabled, 1)
        self._check(grid, "按住热键时才移动", self.hold_to_move, 2)
        self._entry(grid, "移动热键", self.enable_key, 3, "默认 0x06 = XBUTTON2")
        self._scale(grid, "灵敏度", self.sensitivity, 0.01, 2.0, 4)
        self._scale(grid, "平滑", self.smoothing, 0.0, 0.95, 5)
        self._spin(grid, "死区像素", self.deadzone_px, 0, 100, 6)
        self._spin(grid, "单帧最大移动", self.max_step_px, 1, 500, 7)
        self._check(grid, "启用点击", self.click_enabled, 8)
        self._entry(grid, "点击热键", self.click_key, 9, "默认 0x05 = XBUTTON1")

    def _card(self, parent: ttk.Widget, title: str, hint: str) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", columnspan=2)
        ttk.Label(card, text=hint, style="CardHint.TLabel").grid(row=0, column=1, sticky="e")
        return card

    def _entry(self, parent: ttk.Frame, label: str, variable: StringVar, row: int, hint: str = "") -> None:
        ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=7)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=7)
        if hint:
            ttk.Label(parent, text=hint, style="CardHint.TLabel").grid(row=row, column=2, sticky="w", padx=(10, 0))

    def _spin(self, parent: ttk.Frame, label: str, variable: IntVar, from_: int, to: int, row: int) -> None:
        ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=7)
        ttk.Spinbox(parent, textvariable=variable, from_=from_, to=to, width=14).grid(row=row, column=1, sticky="w", pady=7)

    def _scale(self, parent: ttk.Frame, label: str, variable: DoubleVar, from_: float, to: float, row: int) -> None:
        ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=7)
        row_frame = ttk.Frame(parent, style="Card.TFrame")
        row_frame.grid(row=row, column=1, sticky="ew", pady=7)
        ttk.Scale(row_frame, variable=variable, from_=from_, to=to).pack(side="left", fill="x", expand=True)
        ttk.Label(row_frame, textvariable=variable, style="Field.TLabel", width=8).pack(side="left", padx=(10, 0))

    def _combo(self, parent: ttk.Frame, label: str, variable: StringVar, values: list[str], row: int) -> None:
        ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=7)
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=20).grid(
            row=row, column=1, sticky="w", pady=7
        )

    def _check(self, parent: ttk.Frame, label: str, variable: BooleanVar, row: int) -> None:
        ttk.Checkbutton(parent, text=label, variable=variable).grid(row=row, column=1, sticky="w", pady=7)

    def _class_selector(self, parent: ttk.Frame, row: int) -> None:
        ttk.Label(parent, text="目标类别", style="Field.TLabel").grid(row=row, column=0, sticky="nw", pady=7)
        box = ttk.Frame(parent, style="Card.TFrame")
        box.grid(row=row, column=1, sticky="nsew", pady=7)
        box.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(box, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="读取模型类别", command=self.load_model_classes).pack(side="left")
        ttk.Button(toolbar, text="全选", command=self.select_all_classes).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="清空", command=self.clear_classes).pack(side="left", padx=(8, 0))
        ttk.Label(toolbar, textvariable=self.class_status, style="CardHint.TLabel").pack(side="left", padx=(12, 0))

        list_frame = ttk.Frame(box, style="Card.TFrame")
        list_frame.grid(row=1, column=0, sticky="ew")
        list_frame.columnconfigure(0, weight=1)
        self.class_listbox = tk.Listbox(
            list_frame,
            height=8,
            activestyle="none",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#cbd5e1",
            selectbackground="#bfdbfe",
            selectforeground=TEXT,
            font=("Microsoft YaHei UI", 10),
        )
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.class_listbox.yview)
        self.class_listbox.configure(yscrollcommand=scrollbar.set)
        self.class_listbox.grid(row=0, column=0, sticky="ew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.class_listbox.bind("<ButtonRelease-1>", self._toggle_clicked_class)
        self.class_listbox.bind("<space>", self._toggle_active_class)

    def browse_model(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 YOLO 权重",
            filetypes=[("YOLO / ONNX models", "*.pt *.onnx *.engine"), ("All files", "*.*")],
        )
        if path:
            self.model_path.set(path)
            self.load_model_classes()

    def load_model_classes(self) -> None:
        path = self.model_path.get().strip()
        if not path:
            messagebox.showwarning("缺少模型", "请先选择模型文件。")
            return
        if self.loading_model_info:
            self.class_status.set("正在读取，请稍候...")
            return
        self.loading_model_info = True
        self.class_status.set("正在读取类别...")
        self._log(f"正在读取模型类别：{path}")
        threading.Thread(target=self._load_model_classes_worker, args=(path,), daemon=True).start()

    def _load_model_classes_worker(self, path: str) -> None:
        try:
            model_info = self._read_model_info(path)
        except Exception as exc:
            self.root.after(0, lambda: self._model_classes_failed(exc))
            return
        self.root.after(0, lambda: self._set_model_info(model_info))

    def _read_model_info(self, path: str) -> ModelInfo:
        return read_model_info(path)

    def _model_classes_failed(self, exc: Exception) -> None:
        self.loading_model_info = False
        self.class_status.set("读取失败")
        self._log(f"读取模型类别失败：{exc}")
        messagebox.showerror("读取失败", f"无法读取模型类别：\n{exc}")

    def _set_model_info(self, model_info: ModelInfo) -> None:
        self.loading_model_info = False
        self.model_classes = model_info.classes
        self.selected_class_ids.clear()
        if model_info.fixed_imgsz is not None:
            if isinstance(model_info.fixed_imgsz, tuple):
                height, width = model_info.fixed_imgsz
                if height == width:
                    self.imgsz.set(height)
                self._log(f"检测到 ONNX 固定输入尺寸：{format_imgsz(model_info.fixed_imgsz)}")
            else:
                self.imgsz.set(model_info.fixed_imgsz)
                self._log(f"检测到 ONNX 固定输入尺寸：{format_imgsz(model_info.fixed_imgsz)}，已自动更新推理尺寸。")

        if not self.model_classes:
            self.class_status.set("未读到类别；将不过滤")
            self._refresh_class_list()
            self._log("模型未提供类别名称；运行时将不过滤类别。")
            return
        self.class_status.set(f"已读取 {len(self.model_classes)} 个类别；点击可多选")
        self._refresh_class_list()
        self._log(f"已读取 {len(self.model_classes)} 个类别。")

    def _refresh_class_list(self) -> None:
        self._updating_class_list = True
        try:
            self.class_listbox.delete(0, tk.END)
            for idx, (class_id, name) in enumerate(self.model_classes):
                selected = class_id in self.selected_class_ids
                prefix = "✓" if selected else " "
                self.class_listbox.insert(tk.END, f"{prefix} {class_id:>3}  {name}")
                if selected:
                    self.class_listbox.itemconfig(idx, background="#dbeafe", foreground="#172033")
                    self.class_listbox.selection_set(idx)
                else:
                    self.class_listbox.itemconfig(idx, background="#ffffff", foreground="#172033")
        finally:
            self._updating_class_list = False

    def _toggle_clicked_class(self, event: tk.Event) -> str:
        if self._updating_class_list or not self.model_classes:
            return "break"
        index = self.class_listbox.nearest(event.y)
        bbox = self.class_listbox.bbox(index)
        if bbox is None or event.y < bbox[1] or event.y > bbox[1] + bbox[3]:
            return "break"
        if 0 <= index < len(self.model_classes):
            self._toggle_class_index(index)
        return "break"

    def _toggle_active_class(self, event: tk.Event) -> str:
        if self._updating_class_list or not self.model_classes:
            return "break"
        active = self.class_listbox.index(tk.ACTIVE)
        if 0 <= active < len(self.model_classes):
            self._toggle_class_index(active)
        return "break"

    def _toggle_class_index(self, index: int) -> None:
        class_id = self.model_classes[index][0]
        if class_id in self.selected_class_ids:
            self.selected_class_ids.remove(class_id)
        else:
            self.selected_class_ids.add(class_id)
        self._refresh_class_list()
        selected_count = len(self.selected_class_ids)
        if selected_count:
            self.class_status.set(f"已选择 {selected_count} 个类别")
        else:
            self.class_status.set("未选择类别；将不过滤")

    def select_all_classes(self) -> None:
        if not self.model_classes:
            self.class_status.set("请先读取模型类别")
            return
        self.selected_class_ids = {class_id for class_id, _ in self.model_classes}
        self._refresh_class_list()
        self.class_status.set(f"已选择 {len(self.selected_class_ids)} 个类别")

    def clear_classes(self) -> None:
        self.selected_class_ids.clear()
        self._refresh_class_list()
        self.class_status.set("未选择类别；将不过滤")

    def install_dependencies(self) -> None:
        if self.process is not None:
            messagebox.showwarning("正在运行", "请先停止当前控制器。")
            return
        self._start_process([sys.executable, "-m", "pip", "install", "-r", str(PROJECT_ROOT / "requirements.txt")])

    def start_controller(self) -> None:
        if self.process is not None:
            messagebox.showinfo("已经启动", "控制器已经在运行。")
            return
        try:
            config_path = self.save_config()
        except ValueError as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        self._start_process([sys.executable, "-u", "-m", "yolo_mouse_controller", "--config", str(config_path)])

    def stop_controller(self) -> None:
        if self.process is None:
            return
        self.status.set("正在停止")
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.process = None
        self.status.set("已停止")
        self._log("控制器已停止。")

    def save_config(self) -> Path:
        RUNTIME_DIR.mkdir(exist_ok=True)
        config = self._collect_config()
        GENERATED_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        self._log(f"配置已保存：{GENERATED_CONFIG}")
        return GENERATED_CONFIG

    def _collect_config(self) -> dict[str, object]:
        return {
            "capture": {
                "source": self.source.get(),
                "monitor_index": self.monitor_index.get(),
                "device_index": self.device_index.get(),
                "width": self.width.get(),
                "height": self.height.get(),
                "crop_width": self.crop_width.get(),
                "crop_height": self.crop_height.get(),
                "fps": self.fps.get(),
                "region": None,
            },
            "model": {
                "path": self.model_path.get().strip() or "yolov8n.pt",
                "imgsz": self.imgsz.get(),
                "conf": round(float(self.conf.get()), 3),
                "iou": round(float(self.iou.get()), 3),
                "device": self._optional_value(self.device.get()),
            },
            "target": {
                "class_names": self._class_names(),
                "prefer_center": self.prefer_center.get(),
                "aim_offset_x": round(float(self.aim_offset_x.get()), 3),
                "aim_offset_y": round(float(self.aim_offset_y.get()), 3),
                "max_distance_px": self.max_distance_px.get(),
            },
            "mouse": {
                "enabled": self.mouse_enabled.get(),
                "hold_to_move": self.hold_to_move.get(),
                "enable_key": self._parse_key(self.enable_key.get(), "移动热键"),
                "sensitivity": round(float(self.sensitivity.get()), 3),
                "smoothing": round(float(self.smoothing.get()), 3),
                "deadzone_px": self.deadzone_px.get(),
                "max_step_px": self.max_step_px.get(),
                "click_enabled": self.click_enabled.get(),
                "click_key": self._parse_key(self.click_key.get(), "点击热键"),
            },
            "runtime": {
                "preview": self.preview.get(),
                "preview_scale": round(float(self.preview_scale.get()), 3),
                "preview_initial_width": self._effective_preview_width(),
                "preview_initial_height": self._effective_preview_height(),
                "print_fps": self.print_fps.get(),
                "quit_key": "q",
            },
        }

    def _effective_preview_width(self) -> int:
        crop_width = self.crop_width.get()
        if crop_width <= 0:
            return self.width.get()
        return max(1, min(crop_width, self.width.get()))

    def _effective_preview_height(self) -> int:
        crop_height = self.crop_height.get()
        if crop_height <= 0:
            return self.height.get()
        return max(1, min(crop_height, self.height.get()))

    def _class_names(self) -> list[str]:
        if not self.selected_class_ids:
            return []
        selected: list[str] = []
        for class_id, name in self.model_classes:
            if class_id in self.selected_class_ids:
                selected.append(name if name else str(class_id))
        return selected

    def _optional_value(self, raw: str) -> str | int | None:
        value = raw.strip()
        if not value:
            return None
        if value.isdigit():
            return int(value)
        return value

    def _parse_key(self, raw: str, label: str) -> int:
        value = raw.strip()
        if not value:
            raise ValueError(f"{label}不能为空。")
        try:
            return int(value, 0)
        except ValueError as exc:
            raise ValueError(f"{label}需要填写虚拟键码，例如 0x06。") from exc

    def _start_process(self, args: list[str]) -> None:
        self._log("> " + " ".join(f'"{item}"' if " " in item else item for item in args))
        self._reset_metrics()
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        self.process = subprocess.Popen(
            args,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )
        self.status.set("运行中")
        threading.Thread(target=self._read_process_output, daemon=True).start()

    def _reset_metrics(self) -> None:
        self.metric_inference.set("-- ms")
        self.metric_total.set("-- ms")
        self.metric_fps.set("-- FPS")

    def _read_process_output(self) -> None:
        assert self.process is not None
        process = self.process
        if process.stdout is not None:
            for line in process.stdout:
                self.log_queue.put(line.rstrip())
        return_code = process.wait()
        self.log_queue.put(f"进程已退出，代码：{return_code}")
        self.log_queue.put("__PROCESS_DONE__")

    def _poll_logs(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if message == "__PROCESS_DONE__":
                self.process = None
                self.status.set("已停止")
            else:
                self._update_metrics_from_log(message)
                self._log(message)
        self.root.after(100, self._poll_logs)

    def _update_metrics_from_log(self, message: str) -> None:
        if not message.startswith("METRICS "):
            return
        values = dict(re.findall(r"([a-z_]+)=([^\s]+)", message))
        inference_ms = values.get("inference_ms")
        total_ms = values.get("total_ms")
        fps = values.get("fps")
        if inference_ms is not None:
            self.metric_inference.set(f"{float(inference_ms):.2f} ms")
        if total_ms is not None:
            self.metric_total.set(f"{float(total_ms):.2f} ms")
        if fps is not None:
            self.metric_fps.set(f"{float(fps):.1f} FPS")

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def on_close(self) -> None:
        self.stop_controller()
        self.root.destroy()


def main() -> None:
    root = Tk()
    ControlConsole(root)
    root.mainloop()


if __name__ == "__main__":
    main()
