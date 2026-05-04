param(
    [switch]$Install,
    [switch]$Preview,
    [ValidateSet("dxgi", "capture_card")]
    [string]$Source = "",
    [string]$Config = "configs/config.example.yaml"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Test-PythonCommand {
    param([string[]]$Command)

    try {
        $Executable = $Command[0]
        $BaseArgs = if ($Command.Length -gt 1) { $Command[1..($Command.Length - 1)] } else { @() }
        $version = & $Executable @BaseArgs -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $version) {
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

function Get-Python {
    $preferredPython = "D:\06_Environment\python\python.exe"
    if (Test-Path -LiteralPath $preferredPython) {
        return @($preferredPython)
    }

    if (Test-PythonCommand @("python")) {
        return @("python")
    }
    if (Test-PythonCommand @("py", "-3")) {
        return @("py", "-3")
    }

    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $codexPython) {
        return @($codexPython)
    }

    throw @"
未找到可用的 Python。

推荐先执行：
  .\scripts\install-python.ps1

或确认以下路径存在：
  D:\06_Environment\python\python.exe
"@
}

$Python = Get-Python
Push-Location $ProjectRoot
try {
    $env:PYTHONPATH = $ProjectRoot
    $PythonExe = $Python[0]
    $PythonBaseArgs = if ($Python.Length -gt 1) { $Python[1..($Python.Length - 1)] } else { @() }

    if ($Install) {
        & $PythonExe @PythonBaseArgs -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    $ArgsList = @("-m", "yolo_mouse_controller", "--config", $Config)
    if ($Preview) {
        $ArgsList += "--preview"
    }
    if ($Source) {
        $ArgsList += @("--source", $Source)
    }

    & $PythonExe @PythonBaseArgs @ArgsList
} finally {
    Pop-Location
}
