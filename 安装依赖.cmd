@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Setup completed.
echo Create key.md in this folder and put the API key on the first line.
pause
exit /b 0

:failed
echo.
echo Setup failed.
pause
exit /b 1
