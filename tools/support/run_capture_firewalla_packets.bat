@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv_firewalla_capture"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_PROGRESS_BAR=off"
set "PIP_NO_COLOR=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

where python >nul 2>nul
if errorlevel 1 (
  echo Error: Python was not found on PATH.
  echo Install Python 3 and retry.
  exit /b 1
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Creating local virtual environment...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo Error: Failed to create the local virtual environment.
    exit /b 1
  )
)

echo Ensuring pip is available in the local virtual environment...
"%PYTHON_EXE%" -m pip --version >nul 2>nul
if errorlevel 1 (
  "%PYTHON_EXE%" -m ensurepip --upgrade >nul 2>nul
  if errorlevel 1 (
    echo Error: Failed to bootstrap pip in the local virtual environment.
    exit /b 1
  )
)

echo Installing or updating required packages...
"%PYTHON_EXE%" -m pip install --upgrade --quiet pip >nul
"%PYTHON_EXE%" -m pip install --quiet -r "%SCRIPT_DIR%capture_firewalla_packets_requirements.txt"
if errorlevel 1 (
  echo Error: Failed to install required Python packages.
  exit /b 1
)

set "ARGS=%*"
set "HAS_DECODE=0"
echo %* | findstr /i "\-\-decode" >nul
if not errorlevel 1 set "HAS_DECODE=1"

if "%HAS_DECODE%"=="1" (
  echo Running Firewalla packet decode helper...
) else (
  echo Starting Firewalla packet capture helper...
)
"%PYTHON_EXE%" "%SCRIPT_DIR%capture_firewalla_packets.py" %*
exit /b %errorlevel%