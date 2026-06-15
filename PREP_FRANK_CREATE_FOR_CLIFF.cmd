@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0..\readiness-pack-manifest.json" (
  echo.
  echo This launcher is inside an extracted Frank Create readiness pack.
  echo The prep chain can only run from the project root. Opening packaged proof docs instead.
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
echo Running Frank Create Cliff prep...
echo This runs workflow smoke, Demo Doctor, browser QA, Cliff Pack validation, evidence generation, and the one-page call brief.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Test-FrankCreateCliffPrep.ps1"
if errorlevel 1 (
  echo.
  echo Cliff prep did not pass. Review the messages above before the call.
  pause
  exit /b 1
)
echo.
echo Cliff prep passed. Opening the studio and evidence folder.
start "" "http://127.0.0.1:8190/"
start "" "%~dp0user\frank_create\demo_evidence"
pause
