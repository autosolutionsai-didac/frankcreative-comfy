@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0..\readiness-pack-manifest.json" (
  echo.
  echo This launcher is inside an extracted Frank Create readiness pack.
  echo The stop command can only run from the project root. Opening packaged proof docs instead.
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
echo.
echo Stopping Frank Create on port 8190...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Stop-FrankCreate.ps1"
if errorlevel 1 (
  echo.
  echo Frank Create stop failed. Review the messages above.
  pause
  exit /b 1
)
echo.
echo Frank Create stop command finished.
pause
