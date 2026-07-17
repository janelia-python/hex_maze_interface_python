@echo off
setlocal
cd /d "%~dp0"

set "PIXI=pixi"
where pixi >nul 2>nul
if errorlevel 1 (
  if exist "%USERPROFILE%\.pixi\bin\pixi.exe" (
    set "PIXI=%USERPROFILE%\.pixi\bin\pixi.exe"
  ) else (
    echo.
    echo Pixi was not found. Install it from https://pixi.sh/ and then run this file again.
    echo.
    pause
    exit /b 1
  )
)

echo Starting Hex Maze Cluster Control...
echo The first run downloads the application environment and can take a few minutes.
"%PIXI%" run --locked cluster-control
set "exit_code=%ERRORLEVEL%"

if not "%exit_code%"=="0" (
  echo.
  echo Cluster Control exited with error %exit_code%.
  pause
)

exit /b %exit_code%
