$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PreferredPython = "D:\06_Environment\python\python.exe"

if (Test-Path -LiteralPath $PreferredPython) {
    $Python = $PreferredPython
} else {
    $Python = "python"
}

Push-Location $ProjectRoot
try {
    $env:PYTHONPATH = $ProjectRoot
    & $Python -m yolo_mouse_controller.gui
} finally {
    Pop-Location
}
