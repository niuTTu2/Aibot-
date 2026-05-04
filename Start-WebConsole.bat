@echo off
setlocal
cd /d "%~dp0"
start "YOLO Web Console" powershell -NoExit -ExecutionPolicy Bypass -File ".\scripts\web-console.ps1"
timeout /t 2 >nul
start "" http://127.0.0.1:8765/
