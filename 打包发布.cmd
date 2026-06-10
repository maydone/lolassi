@echo off
setlocal
cd /d "%~dp0"

if not exist ".build-venv\Scripts\python.exe" (
    py -3.14 -m venv .build-venv
    if errorlevel 1 (
        echo [ERROR] Python 3.14 is required for packaging.
        pause
        exit /b 1
    )
)

".build-venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :failed

if exist "build" rmdir /s /q "build"
if exist "dist\LOL-Roast-Assistant" rmdir /s /q "dist\LOL-Roast-Assistant"
if exist "LOL-Roast-Assistant.spec" del /q "LOL-Roast-Assistant.spec"

".build-venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --console ^
  --name "LOL-Roast-Assistant" ^
  main.py
if errorlevel 1 goto :failed

copy /y "config.example.json" "dist\LOL-Roast-Assistant\config.json" >nul
copy /y "发布版启动.cmd" "dist\LOL-Roast-Assistant\启动助手.cmd" >nul
copy /y "key.example.md" "dist\LOL-Roast-Assistant\key.example.md" >nul
copy /y "README-发布版.md" "dist\LOL-Roast-Assistant\使用说明.md" >nul
copy /y "LICENSE" "dist\LOL-Roast-Assistant\LICENSE" >nul
copy /y "THIRD_PARTY_NOTICES.md" "dist\LOL-Roast-Assistant\THIRD_PARTY_NOTICES.md" >nul

powershell -NoProfile -Command ^
  "Compress-Archive -Path 'dist\LOL-Roast-Assistant\*' -DestinationPath 'dist\LOL-Roast-Assistant.zip' -Force"
if errorlevel 1 goto :failed

if exist "build" rmdir /s /q "build"
if exist "LOL-Roast-Assistant.spec" del /q "LOL-Roast-Assistant.spec"
if exist "dist\LOL-Roast-Assistant" rmdir /s /q "dist\LOL-Roast-Assistant"
if exist ".build-venv" rmdir /s /q ".build-venv"

echo.
echo Build completed:
echo   dist\LOL-Roast-Assistant.zip
echo.
echo key.md was NOT included.
pause
exit /b 0

:failed
echo.
echo Build failed.
pause
exit /b 1
