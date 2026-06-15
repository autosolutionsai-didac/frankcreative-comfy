@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0..\readiness-pack-manifest.json" (
  echo.
  echo This launcher is inside an extracted Frank Create readiness pack.
  echo The app can only be started from the project root. Opening packaged proof docs instead.
  echo.
  start "" "%~dp0..\OPEN_ME_FIRST.md"
  start "" "%~dp0..\IMPLEMENTATION_MANIFEST.md"
  start "" "%~dp0..\evidence\frank-create-demo-evidence-latest.md"
  start "" "%~dp0..\call-brief\frank-create-call-brief-latest.md"
  start "" "%~dp0..\provider-readiness\frank-create-provider-readiness-latest.md"
  start "" "%~dp0..\activation-checklist\frank-create-activation-checklist-latest.md"
  start "" "%~dp0..\brand-context\frank-create-brand-context-latest.md"
  start "" "%~dp0.."
  pause
  exit /b 0
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-FrankCreate.ps1"
if errorlevel 1 (
  echo.
  echo Frank Create did not start. Check user\frank_create\logs for details.
  pause
  exit /b 1
)
echo.
echo Frank Create is ready. The studio should now be open in your browser.
echo If it did not open, use: http://127.0.0.1:8190/
pause
