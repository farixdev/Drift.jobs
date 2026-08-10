@echo off
REM ============================================================
REM  Drift - one-click launcher for Windows.
REM  Creates the virtual environment + installs dependencies on
REM  first run, then starts the app. Just double-click this file.
REM ============================================================
setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"

REM --- Ensure the virtual environment exists ------------------
if not exist "%PY%" (
    echo [Drift] Creating virtual environment...
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3 -m venv "%VENV%"
    ) else (
        python -m venv "%VENV%"
    )
    if not exist "%PY%" (
        echo.
        echo [Drift] ERROR: could not create the virtual environment.
        echo         Install Python 3.12+ from https://python.org and try again.
        echo.
        pause
        exit /b 1
    )
)

REM --- Ensure dependencies are installed ----------------------
"%PY%" -c "import PyQt5" >nul 2>nul
if %errorlevel% neq 0 (
    echo [Drift] Installing dependencies (first run only, this can take a minute)...
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo [Drift] ERROR: dependency installation failed. See the messages above.
        echo.
        pause
        exit /b 1
    )
)

REM --- Launch -------------------------------------------------
echo [Drift] Starting...
"%PY%" main.py
set "EXITCODE=%errorlevel%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [Drift] The app exited with an error ^(code %EXITCODE%^). See above.
    echo.
    pause
)

endlocal
