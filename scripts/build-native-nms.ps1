$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Source = Join-Path $ProjectRoot "native_console\core\fast_nms.cpp"
$Output = Join-Path $ProjectRoot "yolo_mouse_controller\vision\fast_nms.dll"

$cl = Get-Command cl.exe -ErrorAction SilentlyContinue
if ($cl) {
    Push-Location $ProjectRoot
    try {
        & cl.exe /nologo /std:c++17 /EHsc /O2 /LD /Fe:$Output $Source
    } finally {
        Pop-Location
    }
    Remove-Item (Join-Path $ProjectRoot "yolo_mouse_controller\vision\fast_nms.exp") -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $ProjectRoot "yolo_mouse_controller\vision\fast_nms.lib") -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $ProjectRoot "fast_nms.obj") -ErrorAction SilentlyContinue
    exit $LASTEXITCODE
}

$gxxCommand = Get-Command g++.exe -ErrorAction SilentlyContinue
$knownGxx = "D:\06_Environment\Cpp\mingw64\bin\g++.exe"
$gxx = if ($gxxCommand) { $gxxCommand.Source } elseif (Test-Path -LiteralPath $knownGxx) { $knownGxx } else { $null }
if ($gxx) {
    $mingwBin = Split-Path -Parent $gxx
    $env:PATH = "$mingwBin;$env:PATH"
    & $gxx -shared -static -std=c++17 -O2 -o $Output $Source
    exit $LASTEXITCODE
}

throw "C++ compiler not found. Install MSVC or MinGW-w64."