@echo off
setlocal enabledelayedexpansion
title Bulk MP3 Downloader Studio
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo        🎵 BULK MP3 DOWNLOADER STUDIO 🎵
echo ========================================================
echo.

:: 1. Check for Python executable
set "PYTHON_EXE="

python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
    goto :python_found
)

py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=py -3"
    goto :python_found
)

python3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python3"
    goto :python_found
)

:: Search common Windows Python installation paths
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :python_found
    )
)

for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :python_found
    )
)

:python_not_found
echo [X] ERROR: Python is not installed or not found in system PATH!
echo.
echo     Please install Python 3.10 or newer from:
echo     https://www.python.org/downloads/
echo.
echo     IMPORTANT: During installation, make sure to check:
echo     [x] "Add Python to PATH"
echo.
echo ========================================================
pause
exit /b 1

:python_found
echo [*] Python detected:
%PYTHON_EXE% --version
echo.

:: 2. Check & auto-install dependencies if needed
echo [*] Checking dependencies...
%PYTHON_EXE% -c "import fastapi, uvicorn, yt_dlp, imageio_ffmpeg, pydantic" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] Required libraries missing. Installing requirements from requirements.txt...
    echo [*] This will only take a moment on first launch...
    echo.
    %PYTHON_EXE% -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo.
        echo [!] Warning: Pip install encountered an error. Attempting to start app anyway...
    ) else (
        echo.
        echo [+] All dependencies installed successfully!
    )
)

:: 3. Launch the Application
echo.
echo [*] Launching Bulk MP3 Downloader Studio...
echo [*] Opening browser at http://127.0.0.1:5000 ...
echo ========================================================
echo.

%PYTHON_EXE% app.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo ========================================================
    echo [!] Server stopped with exit code %ERRORLEVEL%.
    echo     If you saw an error above, please verify your Python setup.
    echo ========================================================
    pause
)
