@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Missing .venv. Run setup first:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "key.md" (
    echo [ERROR] Missing key.md.
    echo Create key.md in this folder and put the API key on the first line.
    pause
    exit /b 1
)

title LOL Teammate Comment Assistant
".venv\Scripts\python.exe" main.py

echo.
echo Assistant stopped. Press any key to close.
pause >nul
