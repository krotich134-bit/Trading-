@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

if "%1"=="--clean" (
  if exist dist rmdir /s /q dist
  if exist build rmdir /s /q build
  for /r %%i in (*.egg-info) do rmdir /s /q "%%i"
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python not found on PATH. Install Python 3.11+ and retry.
  exit /b 1
)

python -m pip install --upgrade pip
python -m pip install build wheel
python -m build

echo Build complete. Artifacts in dist\
dir dist\

endlocal

