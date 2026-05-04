$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Server = Join-Path $ProjectRoot "native_console\yolo_web_console.exe"
$KnownMingwBin = "D:\06_Environment\Cpp\mingw64\bin"

if (-not (Test-Path -LiteralPath $Server)) {
    & (Join-Path $PSScriptRoot "build-web-console.ps1")
}

if (Test-Path -LiteralPath $KnownMingwBin) {
    $env:PATH = "$KnownMingwBin;$env:PATH"
}

Push-Location $ProjectRoot
try {
    & $Server --root $ProjectRoot --port 8765
} finally {
    Pop-Location
}
