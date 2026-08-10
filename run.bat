@echo off
REM ============================================================
REM  Drift - one-click launcher for Windows.
REM  First run: creates the venv + installs deps. Then launches.
REM  Just double-click this file.
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"

if exist "%PY%" goto checkdeps

echo [Drift] Creating virtual environment...
py -3 -m venv .venv 1>nul 2>nul
if exist "%PY%" goto checkdeps
python -m venv .venv 1>nul 2>nul
if exist "%PY%" goto checkdeps
echo.
echo [Drift] ERROR: could not create a virtual environment.
echo         Install Python 3.12+ from https://python.org, then run this again.
echo.
pause
goto end

:checkdeps
"%PY%" -c "import PyQt5" 1>nul 2>nul
if not errorlevel 1 goto launch
echo [Drift] Installing dependencies (first run only, this can take a minute)...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt
if not errorlevel 1 goto launch
echo.
echo [Drift] ERROR: dependency installation failed. See the messages above.
echo.
pause
goto end

:launch
echo [Drift] Starting...
"%PY%" main.py
if not errorlevel 1 goto end
echo.
echo [Drift] The app exited with an error. See the messages above.
echo.
pause

:end
endlocal
