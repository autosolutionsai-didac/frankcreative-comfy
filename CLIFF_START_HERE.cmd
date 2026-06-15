@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0..\readiness-pack-manifest.json" (
  echo.
  echo This launcher is inside an extracted Frank Create readiness pack.
  echo Opening packaged proof docs. To run or rebuild the app, use CLIFF_START_HERE.cmd from the project root.
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
echo Frank Create Cliff call-day start.
echo This starts or reuses the local Studio, rebuilds the readiness pack, then opens the studio and handoff docs.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-FrankCreate.ps1" -KeepExisting -NoBrowser
if errorlevel 1 (
  echo.
  echo Frank Create did not start. Review user\frank_create\logs before the call.
  pause
  exit /b 1
)
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Build-FrankCreateReadinessPack.ps1"
if errorlevel 1 (
  echo.
  echo Cliff start failed. Review the messages above before the call.
  pause
  exit /b 1
)
echo.
echo Frank Create is ready for Cliff.
echo Studio: http://127.0.0.1:8190/
echo Readiness pack: user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip
echo Implementation manifest: user\frank_create\readiness_packs\frank-create-implementation-manifest-latest.md
echo Evidence receipt: user\frank_create\demo_evidence\frank-create-demo-evidence-latest.md
echo Call brief: user\frank_create\demo_evidence\frank-create-call-brief-latest.md
echo Provider readiness: user\frank_create\demo_evidence\frank-create-provider-readiness-latest.md
echo Activation checklist: user\frank_create\demo_evidence\frank-create-activation-checklist-latest.md
echo Brand context: user\frank_create\demo_evidence\frank-create-brand-context-latest.md
echo Checksum: user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip.sha256
echo.
start "" "http://127.0.0.1:8190/"
start "" "%~dp0FRANK_CREATE_CALL_DAY.md"
start "" "%~dp0user\frank_create\readiness_packs\frank-create-implementation-manifest-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-demo-evidence-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-call-brief-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-provider-readiness-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-activation-checklist-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-brand-context-latest.md"
start "" "%~dp0user\frank_create\readiness_packs"
exit /b 0
