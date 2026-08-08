@echo off
chcp 65001 >nul
title Sound Isolator
cd /d "%~dp0"

set "PIP_CACHE_DIR=%~dp0cache\pip"
set "TORCH_HOME=%~dp0cache\torch"
set "HF_HOME=%~dp0cache\hf"
set "GRADIO_ANALYTICS_ENABLED=False"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist ".venv\Scripts\python.exe" (
  echo [!] Environment not installed. Run this first:
  echo     powershell -ExecutionPolicy Bypass -File install.ps1
  pause
  exit /b 1
)

echo Opening Sound Isolator ...
".venv\Scripts\python.exe" "src\simple.py"
pause
