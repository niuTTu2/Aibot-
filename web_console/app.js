const defaultConfig = {
  capture: {
    source: "dxgi",
    monitor_index: 0,
    device_index: 0,
    width: 1920,
    height: 1080,
    crop_width: 0,
    crop_height: 0,
    fps: 60,
    region: null
  },
  model: {
    path: "models/sample/yolov8n.onnx",
    imgsz: 640,
    conf: 0.35,
    iou: 0.45,
    device: null
  },
  target: {
    class_names: [],
    prefer_center: true,
    aim_offset_x: 0.5,
    aim_offset_y: 0.5,
    max_distance_px: 900
  },
  mouse: {
    enabled: true,
    hold_to_move: true,
    backend: "sendinput",
    movement_mode: "adaptive",
    lghub_tool_path: "D:\\02_Workspace\\C\\mouse\\lghub_mouse_tool\\build\\lghub_siminput_controller.exe",
    lghub_strict: false,
    lghub_delay_ms: 0,
    lghub_flush_interval_ms: 8,
    enable_keys: [0x06],
    sensitivity: 0.5,
    smoothing: 0.55,
    deadzone_px: 1,
    min_step_px: 1,
    max_step_px: 24,
    max_step_boost: 1.18,
    sticky_radius_px: 95,
    sticky_strength: 1.75,
    pressure_strength: 0.55,
    pressure_cap: 2.2,
    micro_accel: true,
    prediction_ms: 28,
    velocity_assist: 0.45,
    fast_boost: 1.35,
    fast_snap_strength: 0.85,
    fast_snap_threshold: 0.28,
    trigger_enabled: false,
    triggers: [],
    kp: 0.66,
    kp_min: 0.22,
    kp_curve: 0.62,
    kd: 0,
    kd_max_ratio: 0,
    kalman_process_noise: 3.5,
    kalman_measure_noise: 5.0,
    kalman_gate_sigma: 2.5,
    lock_target: true,
    lock_miss_frames: 2,
    feedback_delay_frames: 3,
    feedback_compensation: 0.85,
    weapon_switch_mode: "cycle",
    weapon_next_keys: [0x05],
    weapon_prev_keys: []
  },
  runtime: {
    preview: true,
    preview_scale: 0.5,
    preview_initial_width: 1920,
    preview_initial_height: 1080,
    print_fps: true,
    quit_key: "q"
  }
};

let modelClasses = [];
let selectedClasses = new Set();
let lastLogsText = "";
let lastMouseLogsText = "";
let toastTimer = 0;
let scannedDevices = [
  { label: "Auto", value: "", kind: "auto", available: true },
  { label: "CPU", value: "cpu", kind: "cpu", available: true }
];

const $ = (id) => document.getElementById(id);

const fields = {
  source: $("source"),
  monitorIndex: $("monitorIndex"),
  deviceIndex: $("deviceIndex"),
  width: $("width"),
  height: $("height"),
  cropWidth: $("cropWidth"),
  cropHeight: $("cropHeight"),
  fps: $("fps"),
  preview: $("preview"),
  printFps: $("printFps"),
  previewScale: $("previewScale"),
  previewScaleText: $("previewScaleText"),
  modelPath: $("modelPath"),
  imgsz: $("imgsz"),
  conf: $("conf"),
  iou: $("iou"),
  device: $("device"),
  preferCenter: $("preferCenter"),
  aimOffsetX: $("aimOffsetX"),
  aimOffsetY: $("aimOffsetY"),
  maxDistance: $("maxDistance"),
  classMode: $("classMode"),
  mouseEnabled: $("mouseEnabled"),
  holdToMove: $("holdToMove"),
  mouseBackend: $("mouseBackend"),
  movementMode: $("movementMode"),
  lghubToolPath: $("lghubToolPath"),
  lghubStrict: $("lghubStrict"),
  lghubDelay: $("lghubDelay"),
  lghubFlushInterval: $("lghubFlushInterval"),
  enableKeys: $("enableKeys"),
  sensitivity: $("sensitivity"),
  smoothing: $("smoothing"),
  deadzone: $("deadzone"),
  minStep: $("minStep"),
  maxStep: $("maxStep"),
  maxStepBoost: $("maxStepBoost"),
  lockTarget: $("lockTarget"),
  triggerEnabled: $("triggerEnabled"),
  lockMissFrames: $("lockMissFrames"),
  kp: $("kp"),
  kpMin: $("kpMin"),
  kd: $("kd"),
  stickyRadius: $("stickyRadius"),
  kalmanProcess: $("kalmanProcess"),
  kalmanMeasure: $("kalmanMeasure"),
  kalmanGate: $("kalmanGate"),
  weaponSwitchMode: $("weaponSwitchMode"),
  weaponNextKeys: $("weaponNextKeys"),
  weaponPrevKeys: $("weaponPrevKeys"),
  activeWeaponName: $("activeWeaponName"),
  activeWeaponAim: $("activeWeaponAim"),
  triggersJsonError: $("triggersJsonError"),
  // 兼容性字段（已从 UI 删除，但保留引用避免报错）
  outputScaleX: null,
  outputScaleY: null,
  feedbackDelayFrames: null,
  feedbackCompensation: null,
  kpCurve: null,
  kdMaxRatio: null,
  stickyStrength: null,
  pressureStrength: null,
  pressureCap: null,
  microAccel: null,
  predictionMs: null,
  velocityAssist: null,
  fastBoost: null,
  fastSnapStrength: null,
  fastSnapThreshold: null
};

function ensureMissingFields() {
  // Compatible with cached old index.html + new app.js.
  if (!fields.minStep) {
    fields.minStep = document.createElement("input");
    fields.minStep.type = "number";
    fields.minStep.value = "2";
  }
  if (!fields.stickyRadius) {
    fields.stickyRadius = document.createElement("input");
    fields.stickyRadius.type = "number";
    fields.stickyRadius.value = "90";
  }
  if (!fields.lockMissFrames) {
    fields.lockMissFrames = document.createElement("input");
    fields.lockMissFrames.type = "number";
    fields.lockMissFrames.value = "2";
  }
  if (!fields.weaponSwitchMode) {
    fields.weaponSwitchMode = document.createElement("select");
    fields.weaponSwitchMode.value = "cycle";
  }
  if (!fields.weaponNextKeys) {
    fields.weaponNextKeys = document.createElement("input");
    fields.weaponNextKeys.value = "0x05";
  }
  if (!fields.weaponPrevKeys) {
    fields.weaponPrevKeys = document.createElement("input");
    fields.weaponPrevKeys.value = "";
  }
  // 兼容性字段初始化（已从 UI 删除，创建虚拟 DOM 元素避免报错）
  if (!fields.outputScaleX) {
    fields.outputScaleX = document.createElement("input");
    fields.outputScaleX.type = "number";
    fields.outputScaleX.value = "1.0";
  }
  if (!fields.outputScaleY) {
    fields.outputScaleY = document.createElement("input");
    fields.outputScaleY.type = "number";
    fields.outputScaleY.value = "1.0";
  }
  if (!fields.feedbackDelayFrames) {
    fields.feedbackDelayFrames = document.createElement("input");
    fields.feedbackDelayFrames.type = "number";
    fields.feedbackDelayFrames.value = "0";
  }
  if (!fields.feedbackCompensation) {
    fields.feedbackCompensation = document.createElement("input");
    fields.feedbackCompensation.type = "number";
    fields.feedbackCompensation.value = "0.0";
  }
  // v2 废弃字段（极简控制器不再使用）
  if (!fields.kpCurve) {
    fields.kpCurve = document.createElement("input");
    fields.kpCurve.type = "number";
    fields.kpCurve.value = "1.0";
  }
  if (!fields.kdMaxRatio) {
    fields.kdMaxRatio = document.createElement("input");
    fields.kdMaxRatio.type = "number";
    fields.kdMaxRatio.value = "0.5";
  }
  if (!fields.stickyStrength) {
    fields.stickyStrength = document.createElement("input");
    fields.stickyStrength.type = "number";
    fields.stickyStrength.value = "1.65";
  }
  if (!fields.pressureStrength) {
    fields.pressureStrength = document.createElement("input");
    fields.pressureStrength.type = "number";
    fields.pressureStrength.value = "0.55";
  }
  if (!fields.pressureCap) {
    fields.pressureCap = document.createElement("input");
    fields.pressureCap.type = "number";
    fields.pressureCap.value = "2.2";
  }
  if (!fields.microAccel) {
    fields.microAccel = document.createElement("input");
    fields.microAccel.type = "checkbox";
    fields.microAccel.checked = true;
  }
  if (!fields.predictionMs) {
    fields.predictionMs = document.createElement("input");
    fields.predictionMs.type = "number";
    fields.predictionMs.value = "28";
  }
  if (!fields.velocityAssist) {
    fields.velocityAssist = document.createElement("input");
    fields.velocityAssist.type = "number";
    fields.velocityAssist.value = "0.45";
  }
  if (!fields.fastBoost) {
    fields.fastBoost = document.createElement("input");
    fields.fastBoost.type = "number";
    fields.fastBoost.value = "1.35";
  }
  if (!fields.fastSnapStrength) {
    fields.fastSnapStrength = document.createElement("input");
    fields.fastSnapStrength.type = "number";
    fields.fastSnapStrength.value = "0.85";
  }
  if (!fields.fastSnapThreshold) {
    fields.fastSnapThreshold = document.createElement("input");
    fields.fastSnapThreshold.type = "number";
    fields.fastSnapThreshold.value = "0.28";
  }
}
ensureMissingFields();

const titles = {
  overview: "运行总览",
  capture: "画面采集",
  model: "模型与目标",
  mouse: "鼠标输出",
  logs: "运行日志"
};

function normalizeConfig(config) {
  return {
    capture: { ...defaultConfig.capture, ...(config.capture || {}) },
    model: { ...defaultConfig.model, ...(config.model || {}) },
    target: { ...defaultConfig.target, ...(config.target || {}) },
    mouse: { ...defaultConfig.mouse, ...(config.mouse || {}) },
    runtime: { ...defaultConfig.runtime, ...(config.runtime || {}) }
  };
}

function setConfig(rawConfig) {
  const config = normalizeConfig(rawConfig || defaultConfig);

  fields.source.value = config.capture.source;
  fields.monitorIndex.value = config.capture.monitor_index;
  fields.deviceIndex.value = config.capture.device_index;
  fields.width.value = config.capture.width;
  fields.height.value = config.capture.height;
  fields.cropWidth.value = config.capture.crop_width ?? 0;
  fields.cropHeight.value = config.capture.crop_height ?? 0;
  fields.fps.value = config.capture.fps;
  fields.preview.checked = Boolean(config.runtime.preview);
  fields.printFps.checked = Boolean(config.runtime.print_fps);
  fields.previewScale.value = config.runtime.preview_scale ?? 0.5;
  fields.previewScaleText.textContent = Number(fields.previewScale.value).toFixed(2);

  fields.modelPath.value = config.model.path;
  fields.imgsz.value = Array.isArray(config.model.imgsz) ? config.model.imgsz[0] : config.model.imgsz;
  fields.conf.value = config.model.conf;
  fields.iou.value = config.model.iou;
  setDeviceValue(config.model.device ?? "");

  selectedClasses = new Set(config.target.class_names || []);
  fields.preferCenter.checked = Boolean(config.target.prefer_center);
  fields.aimOffsetX.value = config.target.aim_offset_x ?? 0.5;
  fields.aimOffsetY.value = config.target.aim_offset_y ?? 0.5;
  fields.maxDistance.value = config.target.max_distance_px;

  fields.mouseEnabled.checked = Boolean(config.mouse.enabled);
  fields.holdToMove.checked = Boolean(config.mouse.hold_to_move);
  fields.mouseBackend.value = config.mouse.backend || "sendinput";
  fields.movementMode.value = config.mouse.movement_mode || "adaptive";
  fields.lghubToolPath.value = config.mouse.lghub_tool_path || defaultConfig.mouse.lghub_tool_path;
  fields.lghubStrict.checked = Boolean(config.mouse.lghub_strict);
  fields.lghubDelay.value = config.mouse.lghub_delay_ms ?? 1;
  fields.lghubFlushInterval.value = config.mouse.lghub_flush_interval_ms ?? 8;
  // enable_keys: support both old enable_key (int) and new enable_keys (array)
  const enableKeysRaw = config.mouse.enable_keys ?? (config.mouse.enable_key != null ? [config.mouse.enable_key] : [0x06]);
  fields.enableKeys.value = enableKeysRaw.map(k => "0x" + Number(k).toString(16).padStart(2, "0")).join(",");
  fields.sensitivity.value = config.mouse.sensitivity ?? 0.48;
  fields.smoothing.value = config.mouse.smoothing;
  fields.deadzone.value = config.mouse.deadzone_px ?? 1;
  fields.minStep.value = config.mouse.min_step_px ?? 2;
  fields.maxStep.value = config.mouse.max_step_px ?? 36;
  fields.maxStepBoost.value = config.mouse.max_step_boost ?? 1.45;
  fields.lockTarget.checked = config.mouse.lock_target !== false;
  fields.triggerEnabled.checked = Boolean(config.mouse.trigger_enabled);
  fields.lockMissFrames.value = config.mouse.lock_miss_frames ?? 2;
  fields.kp.value = config.mouse.kp ?? 0.78;
  fields.kpMin.value = config.mouse.kp_min ?? 0.26;
  fields.kpCurve.value = config.mouse.kp_curve ?? 0.55;
  fields.kd.value = config.mouse.kd ?? 0.04;
  fields.kdMaxRatio.value = config.mouse.kd_max_ratio ?? 0.15;
  fields.stickyRadius.value = config.mouse.sticky_radius_px ?? 90;
  fields.stickyStrength.value = config.mouse.sticky_strength ?? 1.65;
  fields.pressureStrength.value = config.mouse.pressure_strength ?? 0.55;
  fields.pressureCap.value = config.mouse.pressure_cap ?? 2.2;
  fields.predictionMs.value = config.mouse.prediction_ms ?? 28;
  fields.velocityAssist.value = config.mouse.velocity_assist ?? 0.45;
  fields.fastBoost.value = config.mouse.fast_boost ?? 1.35;
  fields.fastSnapStrength.value = config.mouse.fast_snap_strength ?? 0.85;
  fields.fastSnapThreshold.value = config.mouse.fast_snap_threshold ?? 0.28;
  fields.kalmanProcess.value = config.mouse.kalman_process_noise ?? 3.5;
  fields.kalmanMeasure.value = config.mouse.kalman_measure_noise ?? 5.0;
  fields.kalmanGate.value = config.mouse.kalman_gate_sigma ?? 2.5;
  // 兼容性字段（已废弃，但保留读取避免报错）
  if (fields.outputScaleX) fields.outputScaleX.value = config.mouse.output_scale_x ?? 1.0;
  if (fields.outputScaleY) fields.outputScaleY.value = config.mouse.output_scale_y ?? 1.0;
  if (fields.feedbackDelayFrames) fields.feedbackDelayFrames.value = config.mouse.feedback_delay_frames ?? 0;
  if (fields.feedbackCompensation) fields.feedbackCompensation.value = config.mouse.feedback_compensation ?? 0.0;
  fields.weaponSwitchMode.value = config.mouse.weapon_switch_mode || "cycle";
  fields.weaponNextKeys.value = formatKeyList(config.mouse.weapon_next_keys ?? [0x05]);
  fields.weaponPrevKeys.value = formatKeyList(config.mouse.weapon_prev_keys ?? []);
  const triggers = config.mouse.triggers ?? [];
  renderTriggers(triggers);
  fields.triggersJsonError.textContent = "";
}

function num(input, fallback = 0) {
  if (input.value.trim() === "") return fallback;
  const value = Number(input.value);
  return Number.isFinite(value) ? value : fallback;
}

function intValue(input, fallback = 0) {
  return Math.trunc(num(input, fallback));
}

function parseKey(text, fallback) {
  const raw = String(text || "").trim();
  if (!raw) return fallback;
  const value = raw.toLowerCase().startsWith("0x") ? parseInt(raw, 16) : parseInt(raw, 10);
  return Number.isFinite(value) ? value : fallback;
}

function parseKeyList(text, fallback = []) {
  const raw = String(text || "").trim();
  if (!raw) return fallback;
  return raw
    .split(",")
    .map((item) => parseKey(item.trim(), 0))
    .filter(Boolean);
}

function formatKeyList(keys = []) {
  return (keys || [])
    .map((key) => "0x" + Number(key).toString(16).padStart(2, "0"))
    .join(",");
}

function effectivePreviewWidth() {
  const width = intValue(fields.width, 1920);
  const crop = intValue(fields.cropWidth, 0);
  return crop > 0 ? Math.min(width, crop) : width;
}

function effectivePreviewHeight() {
  const height = intValue(fields.height, 1080);
  const crop = intValue(fields.cropHeight, 0);
  return crop > 0 ? Math.min(height, crop) : height;
}

function collectConfig() {
  const deviceValue = fields.device.value.trim();
  return {
    capture: {
      source: fields.source.value,
      monitor_index: intValue(fields.monitorIndex),
      device_index: intValue(fields.deviceIndex),
      width: intValue(fields.width, 1920),
      height: intValue(fields.height, 1080),
      crop_width: intValue(fields.cropWidth, 0),
      crop_height: intValue(fields.cropHeight, 0),
      fps: intValue(fields.fps, 60),
      region: null
    },
    model: {
      path: fields.modelPath.value.trim() || "models/sample/yolov8n.onnx",
      imgsz: intValue(fields.imgsz, 640),
      conf: num(fields.conf, 0.35),
      iou: num(fields.iou, 0.45),
      device: deviceValue ? deviceValue : null
    },
    target: {
      class_names: [...selectedClasses],
      prefer_center: fields.preferCenter.checked,
      aim_offset_x: num(fields.aimOffsetX, 0.5),
      aim_offset_y: num(fields.aimOffsetY, 0.5),
      max_distance_px: intValue(fields.maxDistance, 900)
    },
    mouse: {
      enabled: fields.mouseEnabled.checked,
      hold_to_move: fields.holdToMove.checked,
      backend: fields.mouseBackend.value,
      movement_mode: fields.movementMode.value,
      lghub_tool_path: fields.lghubToolPath.value.trim() || defaultConfig.mouse.lghub_tool_path,
      lghub_strict: fields.lghubStrict.checked,
      lghub_delay_ms: intValue(fields.lghubDelay, 1),
      lghub_flush_interval_ms: intValue(fields.lghubFlushInterval, 8),
      enable_keys: parseKeyList(fields.enableKeys.value, [0x06]),
      sensitivity: num(fields.sensitivity, 0.48),
      smoothing: num(fields.smoothing, 0.55),
      deadzone_px: intValue(fields.deadzone, 1),
      min_step_px: intValue(fields.minStep, 2),
      max_step_px: intValue(fields.maxStep, 36),
      max_step_boost: num(fields.maxStepBoost, 1.45),
      trigger_enabled: fields.triggerEnabled.checked,
      lock_target: fields.lockTarget.checked,
      lock_miss_frames: intValue(fields.lockMissFrames, 2),
      kp: num(fields.kp, 0.78),
      kp_min: num(fields.kpMin, 0.26),
      kp_curve: num(fields.kpCurve, 0.55),
      kd: num(fields.kd, 0.04),
      kd_max_ratio: num(fields.kdMaxRatio, 0.15),
      sticky_radius_px: intValue(fields.stickyRadius, 90),
      sticky_strength: num(fields.stickyStrength, 1.65),
      pressure_strength: num(fields.pressureStrength, 0.55),
      pressure_cap: num(fields.pressureCap, 2.2),
      micro_accel: fields.microAccel.checked,
      prediction_ms: num(fields.predictionMs, 28),
      velocity_assist: num(fields.velocityAssist, 0.45),
      fast_boost: num(fields.fastBoost, 1.35),
      fast_snap_strength: num(fields.fastSnapStrength, 0.85),
      fast_snap_threshold: num(fields.fastSnapThreshold, 0.28),
      kalman_process_noise: num(fields.kalmanProcess, 3.5),
      kalman_measure_noise: num(fields.kalmanMeasure, 5.0),
      kalman_gate_sigma: num(fields.kalmanGate, 2.5),
      // 兼容性字段（已废弃，但保留写入避免后端报错）
      output_scale_x: fields.outputScaleX ? num(fields.outputScaleX, 1.0) : 1.0,
      output_scale_y: fields.outputScaleY ? num(fields.outputScaleY, 1.0) : 1.0,
      feedback_delay_frames: fields.feedbackDelayFrames ? intValue(fields.feedbackDelayFrames, 0) : 0,
      feedback_compensation: fields.feedbackCompensation ? num(fields.feedbackCompensation, 0.0) : 0.0,
      weapon_switch_mode: fields.weaponSwitchMode.value || "cycle",
      weapon_next_keys: parseKeyList(fields.weaponNextKeys.value, [0x05]),
      weapon_prev_keys: parseKeyList(fields.weaponPrevKeys.value, []),
      triggers: collectTriggers()
    },
    runtime: {
      preview: fields.preview.checked,
      preview_scale: num(fields.previewScale, 0.5),
      preview_initial_width: effectivePreviewWidth(),
      preview_initial_height: effectivePreviewHeight(),
      print_fps: fields.printFps.checked,
      quit_key: "q"
    }
  };
}

function setDeviceValue(value) {
  const normalized = value === null || value === undefined ? "" : String(value);
  if (![...fields.device.options].some((option) => option.value === normalized)) {
    const option = document.createElement("option");
    option.value = normalized;
    option.textContent = normalized ? `自定义：${normalized}` : "Auto";
    fields.device.appendChild(option);
  }
  fields.device.value = normalized;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { ok: false, error: text };
  }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.message || `\u8bf7\u6c42\u5931\u8d25\uff1a${response.status}`);
  }
  return data;
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

async function withBusy(button, busyText, task) {
  const original = button.textContent;
  button.disabled = true;
  if (busyText) button.textContent = busyText;
  try {
    return await task();
  } finally {
    button.textContent = original;
    button.disabled = false;
  }
}

function showView(view) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === view);
  });
  $("viewTitle").textContent = titles[view] || titles.overview;
}

function renderClasses() {
  const grid = $("classGrid");
  grid.innerHTML = "";

  if (!modelClasses.length) {
    const empty = document.createElement("div");
    empty.className = "class-empty";
    empty.textContent = "未读取类别";
    grid.appendChild(empty);
    $("classSummary").textContent = selectedClasses.size
      ? `已选择 ${selectedClasses.size} 个类别`
      : "未读取类别；空选表示不过滤";
    return;
  }

  for (const item of modelClasses) {
    const name = String(item.name);
    const selected = selectedClasses.has(name);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `class-chip${selected ? " selected" : ""}`;

    const check = document.createElement("span");
    check.className = "check";
    check.textContent = selected ? "✓" : "";
    button.appendChild(check);
    button.appendChild(document.createTextNode(`${item.id} ${name}`));

    button.addEventListener("click", () => {
      if (fields.classMode.value === "single") {
        selectedClasses = selected ? new Set() : new Set([name]);
      } else if (selectedClasses.has(name)) {
        selectedClasses.delete(name);
      } else {
        selectedClasses.add(name);
      }
      renderClasses();
    });
    grid.appendChild(button);
  }

  const count = selectedClasses.size;
  $("classSummary").textContent = count
    ? `已选择 ${count} / ${modelClasses.length} 个类别`
    : `已读取 ${modelClasses.length} 个类别；空选表示不过滤`;
}

async function loadModelInfo() {
  const path = fields.modelPath.value.trim();
  if (!path) throw new Error("请先填写模型路径");
  $("classSummary").textContent = "正在读取模型信息...";
  const previous = new Set(selectedClasses);
  const data = await api(`/api/model-info?path=${encodeURIComponent(path)}`);
  modelClasses = data.classes || [];
  selectedClasses = new Set(modelClasses.map((item) => String(item.name)).filter((name) => previous.has(name)));
  if (data.fixed_imgsz) {
    fields.imgsz.value = Array.isArray(data.fixed_imgsz) ? data.fixed_imgsz[0] : data.fixed_imgsz;
  }
  renderClasses();
  showToast(`已读取 ${modelClasses.length} 个类别`);
}

function renderDevices(devices, notes = []) {
  const current = fields.device.value;
  fields.device.innerHTML = "";
  for (const device of devices) {
    const option = document.createElement("option");
    option.value = device.value ?? "";
    option.textContent = device.label;
    fields.device.appendChild(option);
  }
  setDeviceValue(current);
  if (notes.length) {
    appendLog(notes.join("\n"));
  }
}

async function scanDevices() {
  const data = await api("/api/devices");
  scannedDevices = data.devices || scannedDevices;
  renderDevices(scannedDevices, data.notes || []);
  showToast(`已扫描到 ${scannedDevices.length} 个推理设备选项`);
}

function parseLogFields(line) {
  const values = {};
  const pattern = /([a-zA-Z_]+)=("[^"]*"|\S+)/g;
  let match = pattern.exec(line);
  while (match) {
    values[match[1]] = match[2].replace(/^"|"$/g, "");
    match = pattern.exec(line);
  }
  return values;
}

function renderMouseDiagnostics(lines, running) {
  const mouseLines = lines.filter((line) => line.startsWith("MOUSE_")).slice(-180);
  const output = $("mouseLogs");
  if (!output) return;

  const text = mouseLines.length ? mouseLines.join("\n") : "等待控制器输出鼠标状态...";
  if (text !== lastMouseLogsText) {
    lastMouseLogsText = text;
    output.textContent = text;
    output.scrollTop = output.scrollHeight;
  }

  const latestStatus = [...mouseLines].reverse().find((line) => line.startsWith("MOUSE_STATUS"));
  const latestCommand = [...mouseLines].reverse().find((line) => line.startsWith("MOUSE_CMD"));
  const status = latestStatus ? parseLogFields(latestStatus) : {};
  const command = latestCommand ? parseLogFields(latestCommand) : {};

  $("mouseRuntimeState").textContent = status.state || (running ? "运行中" : "等待数据");
  $("mouseRuntimeHotkey").textContent = status.hotkey_down === undefined ? "--" : (status.hotkey_down === "true" ? "按下" : "未按下");
  $("mouseRuntimeCommand").textContent = command.type
    ? `${command.type}${command.backend ? ` ${command.backend}` : ""}${command.dx ? ` dx=${command.dx} dy=${command.dy || 0}` : ""}`
    : "--";
}

function renderWeaponStatus(lines = [], running = false) {
  const nameEl = fields.activeWeaponName || $("activeWeaponName");
  const aimEl = fields.activeWeaponAim || $("activeWeaponAim");
  if (!nameEl || !aimEl) return;

  const latest = [...lines]
    .reverse()
    .find((line) => line.startsWith("AIM_PROFILE") || line.startsWith("WEAPON_SWITCH"));
  const info = latest ? parseLogFields(latest) : {};
  const fallback = (_triggerData && _triggerData.length) ? _triggerData[0] : null;
  const name = info.name || (fallback ? fallback.name : "");
  const aim = info.aim_offset_y ?? (fallback ? fallback.aim_offset_y : undefined);
  const source = info.source ? ` / ${info.source}` : "";
  const key = info.key ? ` / ${info.key}` : "";

  nameEl.textContent = name ? `${name}${source}${key}` : (running ? "等待档位日志" : "--");
  aimEl.textContent = aim === undefined || aim === null || aim === ""
    ? "aim_offset_y: 全局"
    : `aim_offset_y: ${aim}`;
}

function appendLog(text) {
  const logs = $("logs");
  const next = `${logs.textContent}${logs.textContent ? "\n" : ""}${text}`;
  logs.textContent = next;
  logs.scrollTop = logs.scrollHeight;
}

function updateStatus(status) {
  const running = Boolean(status.running);
  $("runStatus").textContent = running ? "运行中" : "未启动";
  $("statusText").textContent = running ? "控制器正在工作" : "等待启动";
  $("statusDot").classList.toggle("running", running);

  const metrics = status.metrics || {};
  $("metricCapture").textContent = metrics.capture_ms ? `${Number(metrics.capture_ms).toFixed(2)} ms` : "-- ms";
  $("metricInference").textContent = metrics.inference_ms ? `${Number(metrics.inference_ms).toFixed(2)} ms` : "-- ms";
  $("metricTotal").textContent = metrics.total_ms ? `${Number(metrics.total_ms).toFixed(2)} ms` : "-- ms";
  $("metricFps").textContent = metrics.fps ? `${Number(metrics.fps).toFixed(1)} FPS` : "-- FPS";

  if (Array.isArray(status.logs)) {
    renderMouseDiagnostics(status.logs, running);
    renderWeaponStatus(status.logs, running);
    const text = status.logs.join("\n");
    if (text !== lastLogsText) {
      lastLogsText = text;
      const logs = $("logs");
      logs.textContent = text;
      logs.scrollTop = logs.scrollHeight;
    }
  } else {
    renderMouseDiagnostics([], running);
    renderWeaponStatus([], running);
  }
}

async function pollStatus() {
  try {
    updateStatus(await api("/api/status"));
  } catch (error) {
    $("statusText").textContent = error.message;
  }
}

function wireNavigation() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
}

function wireActions() {
  fields.previewScale.addEventListener("input", () => {
    fields.previewScaleText.textContent = Number(fields.previewScale.value).toFixed(2);
  });

  fields.mouseBackend.addEventListener("change", () => {
    if (fields.mouseBackend.value === "lghub_siminput") {
      showToast("将使用罗技 G HUB siminput stream 后端，请确认 lghub_agent.exe 正在运行");
    } else if (fields.mouseBackend.value !== "sendinput") {
      showToast("该鼠标控制后端是预留选项，当前不会发送真实鼠标移动");
    }
  });

  fields.classMode.addEventListener("change", () => {
    if (fields.classMode.value === "single" && selectedClasses.size > 1) {
      selectedClasses = new Set([[...selectedClasses][0]]);
    }
    renderClasses();
  });

  $("browseModelBtn").addEventListener("click", () => withBusy($("browseModelBtn"), "选择中...", async () => {
    const result = await api("/api/browse-model");
    if (result.path) {
      fields.modelPath.value = result.path;
      await loadModelInfo();
    }
  }).catch((error) => showToast(error.message)));

  $("loadClassesBtn").addEventListener("click", () => withBusy($("loadClassesBtn"), "读取中...", loadModelInfo).catch((error) => showToast(error.message)));
  $("scanDevicesBtn").addEventListener("click", () => withBusy($("scanDevicesBtn"), "扫描中...", scanDevices).catch((error) => showToast(error.message)));

  $("selectAllClasses").addEventListener("click", () => {
    selectedClasses = new Set(modelClasses.map((item) => String(item.name)));
    if (fields.classMode.value === "single" && selectedClasses.size > 1) {
      selectedClasses = new Set([[...selectedClasses][0]]);
    }
    renderClasses();
  });

  $("clearClasses").addEventListener("click", () => {
    selectedClasses = new Set();
    renderClasses();
  });

  $("saveBtn").addEventListener("click", () => withBusy($("saveBtn"), "保存中...", async () => {
    await api("/api/config", { method: "POST", body: JSON.stringify(collectConfig()) });
    showToast("配置已保存");
  }).catch((error) => showToast(error.message)));

  $("exportBtn").addEventListener("click", () => Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([JSON.stringify(collectConfig(), null, 2)], { type: 'application/json' })),
    download: 'yolo_config.json'
  }).click());

  $("importBtn").addEventListener("click", () => {
    const input = Object.assign(document.createElement('input'), { type: 'file', accept: '.json' });
    input.onchange = e => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async event => {
        try {
          const config = JSON.parse(event.target.result);
          applyConfig(config);
          showToast("配置导入成功，请注意保存");
        } catch (err) {
          showToast("解析配置文件失败");
        }
      };
      reader.readAsText(file);
    };
    input.click();
  });

  $("startBtn").addEventListener("click", () => withBusy($("startBtn"), "启动中...", async () => {
    await api("/api/start", { method: "POST", body: JSON.stringify(collectConfig()) });
    await pollStatus();
    showToast("控制器已启动");
  }).catch((error) => showToast(error.message)));

  $("stopBtn").addEventListener("click", () => withBusy($("stopBtn"), "停止中...", async () => {
    await api("/api/stop", { method: "POST" });
    await pollStatus();
    showToast("已发送停止指令");
  }).catch((error) => showToast(error.message)));

  $("installBtn").addEventListener("click", () => withBusy($("installBtn"), "安装中...", async () => {
    await api("/api/install", { method: "POST" });
    await pollStatus();
    showToast("依赖安装任务已启动");
  }).catch((error) => showToast(error.message)));

  $("mouseTestBtn").addEventListener("click", () => withBusy($("mouseTestBtn"), "测试中...", async () => {
    const mouse = collectConfig().mouse;
    const query = new URLSearchParams({
      backend: mouse.backend || "sendinput",
      tool: mouse.lghub_tool_path || "",
      strict: mouse.lghub_strict ? "true" : "false",
      delay: String(mouse.lghub_delay_ms ?? 1)
    });
    const result = await api(`/api/mouse-test?${query.toString()}`, { method: "POST" });
    await pollStatus();
    showToast(result.message || (result.skipped ? "当前后端未开发，已跳过移动测试" : "鼠标移动测试完成"));
  }).catch((error) => showToast(error.message)));

  $("clearLogsBtn").addEventListener("click", () => withBusy($("clearLogsBtn"), "清空中...", async () => {
    await api("/api/clear-logs", { method: "POST" });
    lastLogsText = "";
    lastMouseLogsText = "";
    $("logs").textContent = "";
    $("mouseLogs").textContent = "等待控制器输出鼠标状态...";
    showToast("日志已清空");
  }).catch((error) => showToast(error.message)));

  $("addTriggerBtn").addEventListener("click", _addTrigger);
  $("loadDeltaPresetBtn").addEventListener("click", () => {
    renderTriggers(DELTA_FORCE_PRESETS);
    showToast("已载入三角洲行动默认预设");
  });
  $("clearTriggersBtn").addEventListener("click", () => {
    renderTriggers([]);
    showToast("已清空扳机配置");
  });
}

async function init() {
  setConfig(defaultConfig);
  wireNavigation();
  wireActions();
  _wireKeyPicker();
  renderClasses();
  renderDevices(scannedDevices);

  try {
    const saved = await api("/api/config");
    if (saved.config) setConfig(saved.config);
  } catch (error) {
    showToast(error.message);
  }

  renderClasses();
  scanDevices().catch(() => {});
  await pollStatus();
  window.setInterval(pollStatus, 1000);
}

// ─── 扳机可视化 UI ───────────────────────────────────────────────────────────

// 三角洲行动默认预设
const DELTA_FORCE_PRESETS = [
  {
    _label: "突击步枪 / 冲锋枪",
    name: "rifle",
    fire_distance_px: 15,
    trigger_condition: "area",
    fire_area_width_px: 90,
    fire_area_height_px: 90,
    mode: "hold",
    aim_offset_y: null,
    fire_duration_ms: 0,
    settle_delay_ms: 0,
    switch_key: 0x31
  },
  {
    _label: "栓动狙击枪（AWM / M24）",
    name: "bolt",
    fire_distance_px: 5,
    trigger_condition: "distance",
    fire_area_width_px: 70,
    fire_area_height_px: 70,
    mode: "bolt",
    aim_offset_y: null,
    settle_delay_ms: 140,
    bolt_delay_ms: 1200,
    switch_key: 0x32
  },
  {
    _label: "半自动狙 / DMR（SKS / M14）",
    name: "sniper",
    fire_distance_px: 8,
    trigger_condition: "distance",
    fire_area_width_px: 80,
    fire_area_height_px: 80,
    mode: "semi",
    aim_offset_y: null,
    settle_delay_ms: 90,
    switch_key: 0x74
  },
  {
    _label: "手枪（副武器）",
    name: "pistol",
    fire_distance_px: 12,
    trigger_condition: "area",
    fire_area_width_px: 80,
    fire_area_height_px: 80,
    mode: "semi",
    aim_offset_y: null,
    settle_delay_ms: 0,
    switch_key: 0x34
  }
];

const MODE_LABELS = {
  hold:  "按住（步枪/全自动）",
  burst: "连点（连狙/手枪）",
  semi:  "半自动（每次进入范围触发一次）",
  bolt:  "栓动（开火后冷却）"
};

const PRESET_LABELS = {
  rifle:  "rifle — 步枪/全自动",
  sniper: "sniper — 半自动狙",
  pistol: "pistol — 手枪/连狙",
  bolt:   "bolt — 栓动狙击",
  auto:   "auto — 全自动连点"
};

let _triggerData = [];

function renderTriggers(list) {
  _triggerData = list.map(t => ({ ...t }));
  _rebuildTriggerDOM();
}

function _rebuildTriggerDOM() {
  const container = $("triggerList");
  container.innerHTML = "";
  if (_triggerData.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted,#888);font-size:0.85em;margin:0">暂无扳机配置，点击「+ 添加扳机」或载入预设。</p>';
    return;
  }
  _triggerData.forEach((t, idx) => {
    container.appendChild(_buildTriggerCard(t, idx));
  });
}

function _buildTriggerCard(t, idx) {
  const mode = t.mode || "hold";
  const card = document.createElement("div");
  card.style.cssText = "border:1px solid var(--border,#333);border-radius:8px;padding:12px 14px;background:var(--surface2,#1a1a1a);position:relative";

  // Header row
  const header = document.createElement("div");
  header.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:10px";

  const badge = document.createElement("span");
  badge.style.cssText = "font-size:0.75em;font-weight:700;padding:2px 8px;border-radius:4px;background:var(--accent,#e8a020);color:#000;white-space:nowrap";
  badge.textContent = `#${idx + 1}`;

  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.placeholder = "备注（如：步枪）";
  labelInput.value = t._label || "";
  labelInput.style.cssText = "flex:1;font-size:0.9em;padding:4px 8px";
  labelInput.addEventListener("input", () => { _triggerData[idx]._label = labelInput.value; });

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.textContent = "删除";
  delBtn.className = "mini-btn";
  delBtn.style.cssText = "font-size:0.78em;color:#e55;border-color:#e55";
  delBtn.addEventListener("click", () => {
    _triggerData.splice(idx, 1);
    _rebuildTriggerDOM();
  });

  header.append(badge, labelInput, delBtn);

  // Grid of fields
  const grid = document.createElement("div");
  grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:8px 12px";

  function field(labelText, el, hint) {
    const lbl = document.createElement("label");
    lbl.style.cssText = "display:flex;flex-direction:column;gap:3px;font-size:0.82em;color:var(--text-muted,#aaa)";
    if (hint) lbl.title = hint;
    const span = document.createElement("span");
    span.textContent = labelText;
    lbl.append(span, el);
    return lbl;
  }

  function numInput(val, min, max, step, onChange) {
    const el = document.createElement("input");
    el.type = "number"; el.value = val; el.min = min; el.max = max; el.step = step || 1;
    el.style.cssText = "padding:4px 8px;font-size:0.9em";
    el.addEventListener("input", onChange);
    return el;
  }

  function selectInput(options, val, onChange) {
    const el = document.createElement("select");
    el.style.cssText = "padding:4px 8px;font-size:0.9em";
    options.forEach(([v, label]) => {
      const opt = document.createElement("option");
      opt.value = v; opt.textContent = label;
      if (v === val) opt.selected = true;
      el.appendChild(opt);
    });
    el.addEventListener("change", onChange);
    return el;
  }

  // 基础预设
  const presetSel = selectInput(
    Object.entries(PRESET_LABELS),
    t.name || "rifle",
    () => {
      _triggerData[idx].name = presetSel.value;
      // 切换预设时同步默认 mode
      const modeMap = { rifle: "hold", sniper: "semi", pistol: "burst", bolt: "bolt", auto: "burst" };
      _triggerData[idx].mode = modeMap[presetSel.value] || "hold";
      _rebuildTriggerDOM();
    }
  );
  grid.appendChild(field("武器预设", presetSel));

  // Trigger hotkey removed: use movement hotkey enable_keys.

  // 开火距离
  const distInput = numInput(t.fire_distance_px ?? 15, 1, 500, 1, () => {
    _triggerData[idx].fire_distance_px = Number(distInput.value);
  });
  grid.appendChild(field("开火距离 px（距离模式）", distInput, "距离模式：瞄点距屏幕中心 ≤ 此值才开火"));

  const conditionSel = selectInput(
    [
      ["distance", "距离判定"],
      ["area", "范围判定：框进区域即开火"]
    ],
    t.trigger_condition || "distance",
    () => {
      _triggerData[idx].trigger_condition = conditionSel.value;
      _rebuildTriggerDOM();
    }
  );
  grid.appendChild(field("开火判定逻辑", conditionSel, "范围判定不看瞄点距离，只要目标检测框与中心开火区域相交就开火"));

  if ((t.trigger_condition || "distance") === "area") {
    const areaWInput = numInput(t.fire_area_width_px ?? 80, 1, 1000, 1, () => {
      _triggerData[idx].fire_area_width_px = Number(areaWInput.value);
    });
    grid.appendChild(field("开火范围宽 px", areaWInput, "以屏幕/截取画面中心为中心的矩形宽度"));

    const areaHInput = numInput(t.fire_area_height_px ?? 80, 1, 1000, 1, () => {
      _triggerData[idx].fire_area_height_px = Number(areaHInput.value);
    });
    grid.appendChild(field("开火范围高 px", areaHInput, "以屏幕/截取画面中心为中心的矩形高度"));
  }

  const aimYOffsetInput = numInput(t.aim_offset_y ?? 0.5, 0, 1, 0.05, () => {
    const v = Number(aimYOffsetInput.value);
    _triggerData[idx].aim_offset_y = Number.isFinite(v) ? v : null;
  });
  grid.appendChild(field("垂直瞄准点 aim_offset_y", aimYOffsetInput, "每种枪独立设置自瞄 Y 偏移：0=头部，0.5=胸口，1=下缘"));

  const recoilInput = numInput(t.recoil_pull_y ?? 0, 0, 20, 0.1, () => {
    _triggerData[idx].recoil_pull_y = Number(recoilInput.value);
  });
  grid.appendChild(field("压枪力度 recoil_pull_y", recoilInput, "开火时每帧额外向下移动的鼠标单位；0=关闭，步枪可先试 1.0~3.0"));

  const recoilMaxInput = numInput(t.recoil_max_y ?? 8, 0, 30, 0.5, () => {
    _triggerData[idx].recoil_max_y = Number(recoilMaxInput.value);
  });
  grid.appendChild(field("压枪上限 recoil_max_y", recoilMaxInput, "限制压枪单帧最大下拉，避免设置过大导致下压过头"));

  const settleInput = numInput(t.settle_delay_ms ?? 0, 0, 1000, 5, () => {
    _triggerData[idx].settle_delay_ms = Number(settleInput.value);
  });
  grid.appendChild(field("稳定确认 ms", settleInput, "进入开火范围后，需要持续稳定命中这么久才真正开火；栓狙/半狙建议 80~180"));

  // 开火模式
  const modeSel = selectInput(
    Object.entries(MODE_LABELS),
    mode,
    () => {
      _triggerData[idx].mode = modeSel.value;
      _rebuildTriggerDOM();
    }
  );
  grid.appendChild(field("开火模式", modeSel));

  // 模式相关参数
  if (mode === "hold") {
    const durInput = numInput(t.fire_duration_ms ?? 0, 0, 5000, 10, () => {
      _triggerData[idx].fire_duration_ms = Number(durInput.value);
    });
    grid.appendChild(field("按住时长 ms（0=持续按住）", durInput, "0=一直按住左键；>0=按住N毫秒后松开循环（模拟点射）"));
  } else if (mode === "burst" || mode === "auto") {
    const cntInput = numInput(t.burst_count ?? 1, 1, 20, 1, () => {
      _triggerData[idx].burst_count = Number(cntInput.value);
    });
    grid.appendChild(field("连点次数", cntInput));
    const intInput = numInput(t.burst_interval_ms ?? 80, 10, 1000, 5, () => {
      _triggerData[idx].burst_interval_ms = Number(intInput.value);
    });
    grid.appendChild(field("连点间隔 ms", intInput));
  } else if (mode === "bolt") {
    const boltInput = numInput(t.bolt_delay_ms ?? 1200, 100, 5000, 50, () => {
      _triggerData[idx].bolt_delay_ms = Number(boltInput.value);
    });
    grid.appendChild(field("拉栓冷却 ms", boltInput, "开火后等待此时间才能再次开火"));
  }
  // semi: 无额外参数

  // 切换热键（单选）
  const switchKeyWrap = document.createElement("div");
  switchKeyWrap.style.cssText = "grid-column:1/-1;display:flex;align-items:center;gap:8px;margin-top:4px;padding-top:8px;border-top:1px solid var(--border,#333)";
  const switchKeyLabel = document.createElement("span");
  switchKeyLabel.style.cssText = "font-size:0.82em;color:var(--text-muted,#aaa);white-space:nowrap";
  switchKeyLabel.textContent = "切换热键：";
  const switchKeyInput = document.createElement("input");
  switchKeyInput.type = "text";
  switchKeyInput.placeholder = "不绑定";
  switchKeyInput.style.cssText = "flex:1;padding:4px 8px;font-size:0.9em";
  const skv = t.switch_key || 0;
  switchKeyInput.value = skv ? ("0x" + skv.toString(16).padStart(2, "0")) : "";
  switchKeyInput.addEventListener("input", () => {
    const v = switchKeyInput.value.trim();
    if (!v) { _triggerData[idx].switch_key = 0; return; }
    const n = v.toLowerCase().startsWith("0x") ? parseInt(v, 16) : parseInt(v, 10);
    _triggerData[idx].switch_key = Number.isFinite(n) ? n : 0;
  });
  const switchKeyBtn = document.createElement("button");
  switchKeyBtn.type = "button";
  switchKeyBtn.className = "mini-btn";
  switchKeyBtn.textContent = "选择";
  switchKeyBtn.addEventListener("click", () => {
    // 单选模式，选完后回写到 switchKeyInput
    _pickerTargetId = null;
    const tmpId = "__switchKey_" + idx;
    switchKeyInput.id = tmpId;
    openKeyPicker(tmpId, false);
  });
  const switchKeyHint = document.createElement("span");
  switchKeyHint.style.cssText = "font-size:0.78em;color:var(--text-muted,#666)";
  switchKeyHint.textContent = skv ? (VK_LABEL_MAP[skv] || "") : "未绑定";
  switchKeyInput.addEventListener("input", () => {
    const v = switchKeyInput.value.trim();
    const n = v.toLowerCase().startsWith("0x") ? parseInt(v, 16) : parseInt(v, 10);
    switchKeyHint.textContent = (Number.isFinite(n) && n > 0) ? (VK_LABEL_MAP[n] || "") : "未绑定";
  });
  switchKeyWrap.append(switchKeyLabel, switchKeyInput, switchKeyBtn, switchKeyHint);
  grid.appendChild(switchKeyWrap);

  card.append(header, grid);
  return card;
}

function collectTriggers() {
  return _triggerData.map(t => {
    const out = {};
    const keys = ["name", "fire_distance_px", "trigger_condition", "fire_area_width_px", "fire_area_height_px", "mode",
                  "aim_offset_y", "recoil_pull_y", "recoil_max_y", "settle_delay_ms", "fire_duration_ms", "burst_count", "burst_interval_ms", "bolt_delay_ms", "switch_key"];
    keys.forEach(k => { if (t[k] !== undefined) out[k] = t[k]; });
    return out;
  });
}

function _addTrigger() {
  _triggerData.push({
    _label: "",
    name: "rifle",
    fire_distance_px: 15,
    trigger_condition: "area",
    fire_area_width_px: 80,
    fire_area_height_px: 80,
    mode: "hold",
    aim_offset_y: null,
    recoil_pull_y: 0,
    recoil_max_y: 8,
    settle_delay_ms: 0,
    fire_duration_ms: 0
  });
  _rebuildTriggerDOM();
}

// ─────────────────────────────────────────────────────────────────────────────


// --- Key Picker Modal ---------------------------------------------------

const KEY_GROUPS = [
  { label: "鼠标键", keys: [
    { vk: 0x01, label: "左键" }, { vk: 0x02, label: "右键" },
    { vk: 0x04, label: "中键" }, { vk: 0x05, label: "侧键1" }, { vk: 0x06, label: "侧键2" },
  ]},
  { label: "数字键", keys: [0,1,2,3,4,5,6,7,8,9].map((n,i) => ({ vk: 0x30+i, label: String(n) })) },
  { label: "字母键", keys: "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((c,i) => ({ vk: 0x41+i, label: c })) },
  { label: "F键", keys: [1,2,3,4,5,6,7,8,9,10,11,12].map((n,i) => ({ vk: 0x70+i, label: "F"+n })) },
  { label: "修改键", keys: [
    { vk: 0x10, label: "Shift" }, { vk: 0x11, label: "Ctrl" }, { vk: 0x12, label: "Alt" },
    { vk: 0xA0, label: "LShift" }, { vk: 0xA1, label: "RShift" },
    { vk: 0xA2, label: "LCtrl" }, { vk: 0xA3, label: "RCtrl" },
    { vk: 0xA4, label: "LAlt" }, { vk: 0xA5, label: "RAlt" },
  ]},
  { label: "其他键", keys: [
    { vk: 0x20, label: "Space" }, { vk: 0x0D, label: "Enter" }, { vk: 0x1B, label: "Esc" },
    { vk: 0x09, label: "Tab" }, { vk: 0x08, label: "BS" }, { vk: 0x2E, label: "Del" },
    { vk: 0x2D, label: "Ins" }, { vk: 0x24, label: "Home" }, { vk: 0x23, label: "End" },
    { vk: 0x21, label: "PgUp" }, { vk: 0x22, label: "PgDn" },
    { vk: 0x25, label: "←" }, { vk: 0x26, label: "↑" }, { vk: 0x27, label: "→" }, { vk: 0x28, label: "↓" },
    { vk: 0xC0, label: "`" }, { vk: 0xBD, label: "-" }, { vk: 0xBB, label: "=" },
    { vk: 0xDB, label: "[" }, { vk: 0xDD, label: "]" }, { vk: 0xDC, label: "\\" },
    { vk: 0xBA, label: ";" }, { vk: 0xDE, label: "'" }, { vk: 0xBC, label: "," },
    { vk: 0xBE, label: "." }, { vk: 0xBF, label: "/" },
  ]},
  { label: "小键盘", keys: [0,1,2,3,4,5,6,7,8,9].map((n,i) => ({ vk: 0x60+i, label: "Num"+n })).concat([
    { vk: 0x6A, label: "Num*" }, { vk: 0x6B, label: "Num+" },
    { vk: 0x6D, label: "Num-" }, { vk: 0x6E, label: "Num." }, { vk: 0x6F, label: "Num/" },
  ])},
];

const VK_LABEL_MAP = {};
KEY_GROUPS.forEach(g => g.keys.forEach(k => { VK_LABEL_MAP[k.vk] = k.label; }));

let _pickerTargetId = null;
let _pickerMulti = false;
let _pickerCapturing = false;
let _pickerCaptureHandler = null;

function openKeyPicker(inputId, multi = false) {
  _pickerTargetId = inputId;
  _pickerMulti = multi;
  _pickerCapturing = false;
  $("keyPickerCapturing").style.display = "none";
  $("keyPickerCaptureBtn").textContent = "键盘捕获";
  _buildKeyPickerGrid();
  $("keyPickerModal").style.display = "flex";
}

function _buildKeyPickerGrid() {
  const grid = $("keyPickerGrid");
  grid.innerHTML = "";
  const selected = _getSelectedVKs();

  KEY_GROUPS.forEach(group => {
    const header = document.createElement("div");
    header.style.cssText = "grid-column:1/-1;font-size:0.75em;font-weight:700;color:var(--text-muted,#888);padding:6px 0 2px;border-top:1px solid var(--border,#333);margin-top:4px";
    header.textContent = group.label;
    grid.appendChild(header);

    group.keys.forEach(({ vk, label }) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const sel = selected.has(vk);
      btn.style.cssText = `padding:5px 2px;font-size:0.78em;border-radius:5px;border:1px solid ${sel ? "var(--accent,#e8a020)" : "var(--border,#444)"};background:${sel ? "rgba(232,160,32,0.18)" : "var(--surface2,#1a1a1a)"};color:${sel ? "var(--accent,#e8a020)" : "inherit"};cursor:pointer;text-align:center`;
      btn.title = "VK 0x" + vk.toString(16).padStart(2,"0").toUpperCase();
      btn.textContent = label;
      btn.addEventListener("click", () => _pickerToggleKey(vk));
      grid.appendChild(btn);
    });
  });
}

function _getSelectedVKs() {
  const input = $(_pickerTargetId);
  if (!input) return new Set();
  const set = new Set();
  input.value.split(",").forEach(s => {
    const v = s.trim();
    const n = v.toLowerCase().startsWith("0x") ? parseInt(v, 16) : parseInt(v, 10);
    if (Number.isFinite(n) && n > 0) set.add(n);
  });
  return set;
}

function _pickerToggleKey(vk) {
  const input = $(_pickerTargetId);
  if (!input) return;
  const selected = _getSelectedVKs();
  if (selected.has(vk)) { selected.delete(vk); }
  else { if (!_pickerMulti) selected.clear(); selected.add(vk); }
  input.value = [...selected].map(k => "0x" + k.toString(16).padStart(2,"0")).join(",");
  input.dispatchEvent(new Event("input"));
  _buildKeyPickerGrid();
  if (!_pickerMulti) $("keyPickerModal").style.display = "none";
}

function _startCapture() {
  if (_pickerCapturing) { _stopCapture(); return; }
  _pickerCapturing = true;
  $("keyPickerCapturing").style.display = "inline";
  $("keyPickerCaptureBtn").textContent = "停止捕获";

  const VK_FROM_CODE = {
    "KeyA":0x41,"KeyB":0x42,"KeyC":0x43,"KeyD":0x44,"KeyE":0x45,"KeyF":0x46,"KeyG":0x47,
    "KeyH":0x48,"KeyI":0x49,"KeyJ":0x4A,"KeyK":0x4B,"KeyL":0x4C,"KeyM":0x4D,"KeyN":0x4E,
    "KeyO":0x4F,"KeyP":0x50,"KeyQ":0x51,"KeyR":0x52,"KeyS":0x53,"KeyT":0x54,"KeyU":0x55,
    "KeyV":0x56,"KeyW":0x57,"KeyX":0x58,"KeyY":0x59,"KeyZ":0x5A,
    "Digit0":0x30,"Digit1":0x31,"Digit2":0x32,"Digit3":0x33,"Digit4":0x34,
    "Digit5":0x35,"Digit6":0x36,"Digit7":0x37,"Digit8":0x38,"Digit9":0x39,
    "F1":0x70,"F2":0x71,"F3":0x72,"F4":0x73,"F5":0x74,"F6":0x75,
    "F7":0x76,"F8":0x77,"F9":0x78,"F10":0x79,"F11":0x7A,"F12":0x7B,
    "ShiftLeft":0xA0,"ShiftRight":0xA1,"ControlLeft":0xA2,"ControlRight":0xA3,
    "AltLeft":0xA4,"AltRight":0xA5,
    "Space":0x20,"Enter":0x0D,"Escape":0x1B,"Tab":0x09,"Backspace":0x08,
    "Delete":0x2E,"Insert":0x2D,"Home":0x24,"End":0x23,"PageUp":0x21,"PageDown":0x22,
    "ArrowLeft":0x25,"ArrowUp":0x26,"ArrowRight":0x27,"ArrowDown":0x28,
    "Backquote":0xC0,"Minus":0xBD,"Equal":0xBB,"BracketLeft":0xDB,"BracketRight":0xDD,
    "Backslash":0xDC,"Semicolon":0xBA,"Quote":0xDE,"Comma":0xBC,"Period":0xBE,"Slash":0xBF,
    "Numpad0":0x60,"Numpad1":0x61,"Numpad2":0x62,"Numpad3":0x63,"Numpad4":0x64,
    "Numpad5":0x65,"Numpad6":0x66,"Numpad7":0x67,"Numpad8":0x68,"Numpad9":0x69,
    "NumpadMultiply":0x6A,"NumpadAdd":0x6B,"NumpadSubtract":0x6D,"NumpadDecimal":0x6E,"NumpadDivide":0x6F,
  };

  _pickerCaptureHandler = (e) => {
    e.preventDefault();
    const vk = VK_FROM_CODE[e.code];
    if (vk !== undefined) _pickerToggleKey(vk);
  };
  document.addEventListener("keydown", _pickerCaptureHandler);
}

function _stopCapture() {
  _pickerCapturing = false;
  $("keyPickerCapturing").style.display = "none";
  $("keyPickerCaptureBtn").textContent = "键盘捕获";
  if (_pickerCaptureHandler) {
    document.removeEventListener("keydown", _pickerCaptureHandler);
    _pickerCaptureHandler = null;
  }
}

function _wireKeyPicker() {
  $("keyPickerClose").addEventListener("click", () => {
    _stopCapture();
    $("keyPickerModal").style.display = "none";
  });
  $("keyPickerCaptureBtn").addEventListener("click", _startCapture);
  $("keyPickerModal").addEventListener("click", (e) => {
    if (e.target === $("keyPickerModal")) {
      _stopCapture();
      $("keyPickerModal").style.display = "none";
    }
  });
}

// -------------------------------------------------------------------------

window.addEventListener("DOMContentLoaded", () => {
  init().catch((error) => showToast(error.message));
});


