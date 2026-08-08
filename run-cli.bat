@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PIP_CACHE_DIR=%~dp0cache\pip"
set "TORCH_HOME=%~dp0cache\torch"
set "HF_HOME=%~dp0cache\hf"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist ".venv\Scripts\python.exe" (
  echo [!] Environment not installed. Run install.ps1 first.
  exit /b 1
)

".venv\Scripts\python.exe" "src\cli.py" %*
