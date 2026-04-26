param(
    [string]$TargetDir = "D:\06_Environment\python",
    [string]$InstallerPath = "D:\06_Environment\python-3.12.10-amd64.exe"
)

$ErrorActionPreference = "Stop"
$PythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$PythonExe = Join-Path $TargetDir "python.exe"

if (Test-Path -LiteralPath $PythonExe) {
    & $PythonExe --version
    Write-Host "Python already exists at $PythonExe"
    exit 0
}

New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $InstallerPath) -Force | Out-Null

if (-not (Test-Path -LiteralPath $InstallerPath)) {
    Write-Host "Downloading Python 3.12.10 installer..."
    Invoke-WebRequest -Uri $PythonUrl -OutFile $InstallerPath
}

Write-Host "Installing Python to $TargetDir ..."
$args = @(
    "/quiet",
    "InstallAllUsers=0",
    "TargetDir=$TargetDir",
    "Include_pip=1",
    "Include_launcher=0",
    "PrependPath=0",
    "Shortcuts=0"
)

$process = Start-Process -FilePath $InstallerPath -ArgumentList $args -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Python installer failed with exit code $($process.ExitCode)."
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Install finished, but python.exe was not found at $PythonExe."
}

& $PythonExe --version
& $PythonExe -m pip --version
Write-Host "Python is ready at $PythonExe"
