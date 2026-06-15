@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0..\readiness-pack-manifest.json" (
  echo.
  echo This launcher is inside an extracted Frank Create readiness pack.
  echo The pack has already been built and verified on Didac's workstation.
  echo Opening packaged proof docs. To rerun verification, use VERIFY_CLIFF_PACK.cmd from the project root.
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
echo Verifying latest Frank Create Cliff readiness pack...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Verify-FrankCreateReadinessPack.ps1"
if errorlevel 1 (
  echo.
  echo Readiness pack verification failed. Rebuild it with CLIFF_START_HERE.cmd or BUILD_FRANK_CREATE_READINESS_PACK.cmd.
  pause
  exit /b 1
)
echo.
echo Readiness pack verification passed.
echo Send or open: user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip
pause
