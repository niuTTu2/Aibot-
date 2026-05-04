$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Source = Join-Path $ProjectRoot "native_console\server.cpp"
$Output = Join-Path $ProjectRoot "native_console\yolo_web_console.exe"
$BuildTemp = Join-Path $ProjectRoot ".runtime\build-temp"

New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null
New-Item -ItemType Directory -Path $BuildTemp -Force | Out-Null
$env:TMP = $BuildTemp
$env:TEMP = $BuildTemp

$cl = Get-Command cl.exe -ErrorAction SilentlyContinue
if ($cl) {
    Push-Location $ProjectRoot
    try {
        & cl.exe /nologo /std:c++17 /EHsc /O2 /utf-8 /Fe:$Output $Source ws2_32.lib shell32.lib comdlg32.lib
    } finally {
        Pop-Location
    }
    exit $LASTEXITCODE
}

$gxxCommand = Get-Command g++.exe -ErrorAction SilentlyContinue
$knownGxx = "D:\06_Environment\Cpp\mingw64\bin\g++.exe"
$gxx = if ($gxxCommand) { $gxxCommand.Source } elseif (Test-Path -LiteralPath $knownGxx) { $knownGxx } else { $null }
if ($gxx) {
    $mingwBin = Split-Path -Parent $gxx
    $env:PATH = "$mingwBin;$env:PATH"
    & $gxx -std=c++17 -O2 -o $Output $Source -lws2_32 -lshell32 -lcomdlg32
    exit $LASTEXITCODE
}

throw "C++ compiler not found. Install Visual Studio Build Tools or MinGW-w64 with g++."
