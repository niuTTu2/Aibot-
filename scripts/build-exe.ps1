param(
    [string]$OutputName = "YoloMouseController",
    [switch]$NoConsole
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistPath = Join-Path $ProjectRoot "artifacts\pyinstaller\dist"
$WorkPath = Join-Path $ProjectRoot "artifacts\pyinstaller\build"
$SpecPath = Join-Path $ProjectRoot "packaging\pyinstaller"

Push-Location $ProjectRoot
try {
    Write-Host ">>> [1/3] 查找 Python 并安装 PyInstaller..." -ForegroundColor Cyan

    $PythonExe = "python"
    if (Test-Path -LiteralPath "D:\06_Environment\python\python.exe") {
        $PythonExe = "D:\06_Environment\python\python.exe"
    }

    & $PythonExe -m pip install pyinstaller --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 安装失败，请检查 Python 环境。"
    }

    Write-Host ">>> [2/3] 开始打包 EXE..." -ForegroundColor Cyan

    New-Item -ItemType Directory -Force -Path $DistPath | Out-Null
    New-Item -ItemType Directory -Force -Path $WorkPath | Out-Null
    New-Item -ItemType Directory -Force -Path $SpecPath | Out-Null

    $ArgsList = @(
        "--name", $OutputName,
        "--onefile",
        "--clean",
        "--noconfirm",
        "--distpath", $DistPath,
        "--workpath", $WorkPath,
        "--specpath", $SpecPath,
        "--add-data", "web_console;web_console",
        "--add-data", "configs\config.example.yaml;configs",
        "--add-data", "models\sample\yolov8n.onnx;models\sample",
        "--add-data", "models\sample\yolov8n.pt;models\sample"
    )

    if ($NoConsole) {
        $ArgsList += "--noconsole"
    }

    & $PythonExe -m PyInstaller @ArgsList yolo_mouse_controller\__main__.py
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    Write-Host ">>> [3/3] 打包完成：$DistPath\$OutputName.exe" -ForegroundColor Green
} finally {
    Pop-Location
}
