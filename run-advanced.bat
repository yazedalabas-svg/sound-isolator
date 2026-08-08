@echo off
chcp 65001 >nul
title Sound Isolator - Advanced
cd /d "%~dp0"

set "PIP_CACHE_DIR=%~dp0cache\pip"
set "TORCH_HOME=%~dp0cache\torch"
set "HF_HOME=%~dp0cache\hf"
set "GRADIO_ANALYTICS_ENABLED=False"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist ".venv\Scripts\python.exe" (
  echo [!] Environment not installed. Run install.ps1 first.
  pause
  exit /b 1
)

echo Opening Sound Isolator (advanced mode) ...
".venv\Scripts\python.exe" "src\gui.py"
pause
