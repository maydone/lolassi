@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

if not exist "key.md" (
    echo [ERROR] Missing key.md.
    echo Rename key.example.md to key.md and put your API key on the first line.
    pause
    exit /b 1
)

"LOL-Roast-Assistant.exe"

echo.
echo Assistant stopped. Press any key to close.
pause >nul

