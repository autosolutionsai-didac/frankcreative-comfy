@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0..\readiness-pack-manifest.json" (
  echo.
  echo This launcher is inside an extracted Frank Create readiness pack.
  echo The pack is already built. Opening packaged proof docs instead.
  echo To rebuild, use BUILD_FRANK_CREATE_READINESS_PACK.cmd from the project root.
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
echo Building Frank Create Cliff readiness pack...
echo This runs Cliff prep, then zips the call brief, evidence, receipts, runbook, QA screenshots, and validated Cliff handoff.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Build-FrankCreateReadinessPack.ps1"
if errorlevel 1 (
  echo.
  echo Readiness pack failed. Review the messages above.
  pause
  exit /b 1
)
echo.
echo Readiness pack created: user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip
echo Opening the readiness folder, implementation manifest, evidence receipt, one-page call brief, provider-readiness receipt, activation checklist, and brand-context brief.
start "" "%~dp0user\frank_create\readiness_packs"
start "" "%~dp0user\frank_create\readiness_packs\frank-create-implementation-manifest-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-demo-evidence-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-call-brief-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-provider-readiness-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-activation-checklist-latest.md"
start "" "%~dp0user\frank_create\demo_evidence\frank-create-brand-context-latest.md"
pause
