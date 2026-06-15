from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def assert_extracted_pack_guard(text: str, launcher_name: str) -> None:
    assert 'if exist "%~dp0..\\readiness-pack-manifest.json"' in text
    assert "Opening packaged proof docs" in text
    assert f"use {launcher_name} from the project root" in text or "can only" in text
    assert 'start "" "%~dp0..\\OPEN_ME_FIRST.md"' in text
    assert 'start "" "%~dp0..\\IMPLEMENTATION_MANIFEST.md"' in text
    assert 'start "" "%~dp0..\\evidence\\frank-create-demo-evidence-latest.md"' in text
    assert 'start "" "%~dp0..\\call-brief\\frank-create-call-brief-latest.md"' in text
    assert 'start "" "%~dp0..\\provider-readiness\\frank-create-provider-readiness-latest.md"' in text
    assert 'start "" "%~dp0..\\activation-checklist\\frank-create-activation-checklist-latest.md"' in text
    assert 'start "" "%~dp0..\\brand-context\\frank-create-brand-context-latest.md"' in text


def test_demo_launcher_starts_frank_create_server():
    script = ROOT / "scripts" / "Start-FrankCreate.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "main.py" in text
    assert "--port" in text
    assert "--front-end-root" in text
    assert "frank-create\\dist" in text
    assert "/api/frank/health" in text
    assert "Start-Process" in text
    assert "Start-Process $StudioUrl -ErrorAction Stop" in text
    assert "Could not open the browser automatically. Use: $StudioUrl" in text
    assert "Opening studio in your default browser" in text
    assert "http://127.0.0.1" in text


def test_demo_launcher_reuses_healthy_server_when_keep_existing_is_set():
    script = ROOT / "scripts" / "Start-FrankCreate.ps1"

    text = script.read_text(encoding="utf-8")

    assert "KeepExisting" in text
    assert "if ($KeepExisting -and !$ResetDemoData)" in text
    assert "Reusing healthy Frank Create server" in text
    assert "No healthy existing server found" in text
    assert "Publish-ReadyAndExit" in text
    assert text.index("if ($KeepExisting -and !$ResetDemoData)") < text.index('Write-Step "Starting ComfyUI with Frank Create shell')


def test_demo_launcher_resets_seed_data_after_stopping_existing_server():
    script = ROOT / "scripts" / "Start-FrankCreate.ps1"

    text = script.read_text(encoding="utf-8")

    stop_index = text.index('Write-Step "Stopping existing server on port $Port..."')
    reset_index = text.index('Write-Step "Resetting Frank demo sessions and seeding a clean starter brief..."')
    start_index = text.index('Write-Step "Starting ComfyUI with Frank Create shell on port $Port..."')

    assert stop_index < reset_index < start_index


def test_demo_launcher_only_stops_python_main_processes_for_target_port():
    script = ROOT / "scripts" / "Start-FrankCreate.ps1"

    text = script.read_text(encoding="utf-8")

    assert "function Get-FrankServerProcess" in text
    assert '$_.Name -like "python*"' in text
    assert "main\\.py" in text
    assert "--port\\s+$Port" in text
    assert '*main.py --port $Port*' not in text


def test_stop_launcher_only_stops_frank_create_processes_for_target_port():
    script = ROOT / "scripts" / "Stop-FrankCreate.ps1"
    wrapper = ROOT / "STOP_FRANK_CREATE.cmd"

    assert script.exists()
    assert wrapper.exists()
    text = script.read_text(encoding="utf-8")
    wrapper_text = wrapper.read_text(encoding="utf-8")

    assert "function Get-FrankServerProcess" in text
    assert '$_.Name -like "python*"' in text
    assert "main\\.py" in text
    assert "--port\\s+$Port" in text
    assert "Stop-Process -Id $process.ProcessId -Force" in text
    assert "No Frank Create server process found" in text
    assert "Stop-FrankCreate.ps1" in wrapper_text
    assert "Stopping Frank Create on port 8190" in wrapper_text
    assert_extracted_pack_guard(wrapper_text, "STOP_FRANK_CREATE.cmd")
    assert "pause" in wrapper_text


def test_demo_launcher_can_reset_seed_data():
    script = ROOT / "scripts" / "Start-FrankCreate.ps1"
    reset_script = ROOT / "scripts" / "reset_frank_demo.py"

    text = script.read_text(encoding="utf-8")
    reset_text = reset_script.read_text(encoding="utf-8")

    assert "ResetDemoData" in text
    assert "reset_frank_demo.py" in text
    assert "sys.path.insert" in reset_text
    assert "--root" in reset_text
    assert "reset_and_seed_demo" in reset_text
    assert "Seeded demo assets" in reset_text
    assert "Seeded demo motion assets" in reset_text


def test_demo_launcher_loads_server_side_provider_env_file():
    script = ROOT / "scripts" / "Start-FrankCreate.ps1"

    text = script.read_text(encoding="utf-8")

    assert "provider_keys.env" in text
    assert "function Test-ProviderEnvValueReal" in text
    assert "Test-ProviderEnvValueReal -Value $value" in text
    assert "your_key_here" in text
    assert 'StartsWith("paste ")' in text
    assert "$currentEnv = Get-Item" in text
    assert "Test-ProviderEnvValueReal -Value $currentEnv.Value" in text
    assert "$ConfiguredProviderKeys = @($ProviderEnvNames | Where-Object" in text
    assert "$MissingProviderKeys = @($ProviderEnvNames | Where-Object" in text
    assert "Test-ProviderEnvValueReal -Value $item.Value" in text
    assert 'Set-Item -Path "Env:$name"' in text
    assert "GOOGLE_API_KEY" in text
    assert "REPLICATE_API_TOKEN" in text
    assert "OPENAI_API_KEY" in text
    assert "RUNWAYML_API_SECRET" not in text
    assert "RUNWAY_API_KEY" not in text


def test_demo_launcher_rebuilds_stale_frontend_dist():
    script = ROOT / "scripts" / "Start-FrankCreate.ps1"

    text = script.read_text(encoding="utf-8")

    assert "function Test-FrankFrontendBuildStale" in text
    assert "LastWriteTimeUtc" in text
    assert "Frontend build missing or stale. Building Frank shell" in text
    assert "$FrontendNeedsBuild = Test-FrankFrontendBuildStale" in text
    assert "if (!$NoBuild -and $FrontendNeedsBuild)" in text
    assert 'Join-Path $FrontendRoot "src"' in text
    assert 'Join-Path $FrontendRoot "index.html"' in text
    assert 'Join-Path $FrontendRoot "package-lock.json"' in text
    assert 'Join-Path $FrontendRoot "vite.config.ts"' in text
    assert "Get-ChildItem -LiteralPath $path -Recurse -File" in text
    assert "npm run build" in text


def test_provider_env_example_has_placeholders_only():
    example = ROOT / "config" / "frank-create.env.example"

    assert example.exists()
    text = example.read_text(encoding="utf-8")

    for env_var in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "REPLICATE_API_TOKEN"):
        assert f"{env_var}=" in text
    for env_var in (
        "FAL_KEY",
        "RECRAFT_API_KEY",
        "RECRAFT_API_TOKEN",
        "IDEOGRAM_API_KEY",
        "XAI_API_KEY",
        "RUNWAYML_API_SECRET",
        "RUNWAY_API_KEY",
    ):
        assert f"{env_var}=" not in text
    assert "r8_" not in text
    assert "sk-" not in text


def test_call_day_docs_and_pack_scripts_describe_three_provider_boundary():
    checked_paths = [
        ROOT / "FRANK_CREATE_DEMO.md",
        ROOT / "FRANK_CREATE_CALL_DAY.md",
        ROOT / "OPEN_FOR_CLIFF.md",
        ROOT / "scripts" / "Build-FrankCreateReadinessPack.ps1",
        ROOT / "scripts" / "Verify-FrankCreateReadinessPack.ps1",
        ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1",
    ]
    forbidden = (
        "FAL_KEY",
        "RECRAFT_API_KEY",
        "RECRAFT_API_TOKEN",
        "IDEOGRAM_API_KEY",
        "XAI_API_KEY",
        "RUNWAYML_API_SECRET",
        "RUNWAY_API_KEY",
        "Runway",
        "Grok",
        "Recraft",
        "Ideogram",
        "fal.ai",
    )

    for path in checked_paths:
        text = path.read_text(encoding="utf-8")
        assert "GOOGLE_API_KEY" in text
        assert "OPENAI_API_KEY" in text
        assert "REPLICATE_API_TOKEN" in text
        for stale in forbidden:
            assert stale not in text, f"{path.name} still mentions {stale}"


def test_double_click_wrapper_points_to_demo_launcher():
    wrapper = ROOT / "START_FRANK_CREATE.cmd"

    assert wrapper.exists()
    text = wrapper.read_text(encoding="utf-8")

    assert "Start-FrankCreate.ps1" in text
    assert "ExecutionPolicy Bypass" in text
    assert_extracted_pack_guard(text, "START_FRANK_CREATE.cmd")


def test_double_click_wrapper_opens_studio_after_health_check():
    wrapper = ROOT / "START_FRANK_CREATE.cmd"

    text = wrapper.read_text(encoding="utf-8")

    assert "-NoBrowser" not in text
    assert 'start "" "http://127.0.0.1:8190/"' not in text
    assert "The studio should now be open in your browser" in text
    assert "If it did not open, use: http://127.0.0.1:8190/" in text
    assert "pause" in text
    assert "Frank Create is ready" in text
    assert_extracted_pack_guard(text, "START_FRANK_CREATE.cmd")


def test_double_click_demo_wrapper_lets_launcher_open_browser_after_health_check():
    wrapper = ROOT / "START_FRANK_CREATE_DEMO.cmd"

    text = wrapper.read_text(encoding="utf-8")

    assert "-ResetDemoData" in text
    assert "-NoBrowser" not in text
    assert 'start "" "http://127.0.0.1:8190/"' not in text
    assert "The studio should now be open in your browser" in text
    assert "If it did not open, use: http://127.0.0.1:8190/" in text
    assert "pause" in text
    assert_extracted_pack_guard(text, "START_FRANK_CREATE_DEMO.cmd")


def test_double_click_cliff_prep_wrapper_runs_full_chain_and_opens_evidence():
    wrapper = ROOT / "PREP_FRANK_CREATE_FOR_CLIFF.cmd"

    assert wrapper.exists()
    text = wrapper.read_text(encoding="utf-8")

    assert "Test-FrankCreateCliffPrep.ps1" in text
    assert "ExecutionPolicy Bypass" in text
    assert "workflow smoke, Demo Doctor, browser QA, Cliff Pack validation, evidence generation, and the one-page call brief" in text
    assert 'start "" "http://127.0.0.1:8190/"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence"' in text
    assert_extracted_pack_guard(text, "PREP_FRANK_CREATE_FOR_CLIFF.cmd")
    assert "pause" in text


def test_double_click_readiness_pack_wrapper_builds_shareable_zip():
    wrapper = ROOT / "BUILD_FRANK_CREATE_READINESS_PACK.cmd"

    assert wrapper.exists()
    text = wrapper.read_text(encoding="utf-8")

    assert "Build-FrankCreateReadinessPack.ps1" in text
    assert "ExecutionPolicy Bypass" in text
    assert_extracted_pack_guard(text, "BUILD_FRANK_CREATE_READINESS_PACK.cmd")
    assert "use BUILD_FRANK_CREATE_READINESS_PACK.cmd from the project root" in text
    assert "call brief, evidence, receipts, runbook, QA screenshots, and validated Cliff handoff" in text
    assert 'start "" "%~dp0user\\frank_create\\readiness_packs"' in text
    assert 'start "" "%~dp0user\\frank_create\\readiness_packs\\frank-create-implementation-manifest-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-demo-evidence-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-call-brief-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-provider-readiness-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-activation-checklist-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-brand-context-latest.md"' in text
    assert "Opening the readiness folder, implementation manifest, evidence receipt, one-page call brief, provider-readiness receipt, activation checklist, and brand-context brief" in text
    assert "frank-create-cliff-readiness-latest.zip" in text
    assert "frank-create-implementation-manifest-latest.md" in text
    assert "frank-create-cliff-readiness-latest.zip" in (ROOT / "scripts" / "Build-FrankCreateReadinessPack.ps1").read_text(encoding="utf-8")
    assert "pause" in text


def test_double_click_cliff_start_here_runs_full_call_day_path():
    wrapper = ROOT / "CLIFF_START_HERE.cmd"

    assert wrapper.exists()
    text = wrapper.read_text(encoding="utf-8")

    assert "Build-FrankCreateReadinessPack.ps1" in text
    assert "Start-FrankCreate.ps1" in text
    assert "-KeepExisting -NoBrowser" in text
    assert "ExecutionPolicy Bypass" in text
    assert_extracted_pack_guard(text, "CLIFF_START_HERE.cmd")
    assert "use CLIFF_START_HERE.cmd from the project root" in text
    assert "starts or reuses the local Studio, rebuilds the readiness pack" in text
    assert "Frank Create did not start" in text
    assert "Frank Create is ready for Cliff" in text
    assert "frank-create-cliff-readiness-latest.zip" in text
    assert "frank-create-cliff-readiness-latest.zip.sha256" in text
    assert "frank-create-implementation-manifest-latest.md" in text
    assert "frank-create-demo-evidence-latest.md" in text
    assert "Call brief: user\\frank_create\\demo_evidence\\frank-create-call-brief-latest.md" in text
    assert "Provider readiness: user\\frank_create\\demo_evidence\\frank-create-provider-readiness-latest.md" in text
    assert "frank-create-brand-context-latest.md" in text
    assert 'start "" "http://127.0.0.1:8190/"' in text
    assert 'start "" "%~dp0FRANK_CREATE_CALL_DAY.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\readiness_packs\\frank-create-implementation-manifest-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-demo-evidence-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-call-brief-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-provider-readiness-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-activation-checklist-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\demo_evidence\\frank-create-brand-context-latest.md"' in text
    assert 'start "" "%~dp0user\\frank_create\\readiness_packs"' in text
    assert "pause" in text
    assert text.index("Start-FrankCreate.ps1") < text.index("Build-FrankCreateReadinessPack.ps1")


def test_root_open_for_cliff_note_is_short_and_actionable():
    note = ROOT / "OPEN_FOR_CLIFF.md"

    assert note.exists()
    text = note.read_text(encoding="utf-8")

    assert "Double-click `CLIFF_START_HERE.cmd`." in text
    assert "starts or reuses the local Studio, runs prep, rebuilds the readiness pack" in text
    assert "frank-create-implementation-manifest-latest.md" in text
    assert "frank-create-demo-evidence-latest.md" in text
    assert "frank-create-cliff-readiness-latest.zip" in text
    assert "frank-create-cliff-readiness-latest.zip.sha256" in text
    assert "expected warnings are okay" in text.lower()
    assert "GOOGLE_API_KEY" in text
    assert "Gemini/Nano Banana is the first live API path" in text
    assert "reference upload, generate, edit, approve, export, storyboard, and handoff" in text


def test_double_click_quick_check_wrapper_runs_demo_doctor():
    wrapper = ROOT / "CHECK_FRANK_CREATE.cmd"

    assert wrapper.exists()
    text = wrapper.read_text(encoding="utf-8")

    assert "Test-FrankCreateDemo.ps1" in text
    assert "-StartIfDown" in text
    assert "ExecutionPolicy Bypass" in text
    assert "Checking Frank Create demo readiness" in text
    assert "Frank Create quick check passed. Open: http://127.0.0.1:8190/" in text
    assert "Frank Create is not ready" in text
    assert_extracted_pack_guard(text, "CHECK_FRANK_CREATE.cmd")
    assert "pause" in text


def test_verify_cliff_pack_wrapper_checks_latest_zip_without_rebuild():
    wrapper = ROOT / "VERIFY_CLIFF_PACK.cmd"
    script = ROOT / "scripts" / "Verify-FrankCreateReadinessPack.ps1"

    assert wrapper.exists()
    assert script.exists()
    wrapper_text = wrapper.read_text(encoding="utf-8")
    script_text = script.read_text(encoding="utf-8")

    assert "Verify-FrankCreateReadinessPack.ps1" in wrapper_text
    assert_extracted_pack_guard(wrapper_text, "VERIFY_CLIFF_PACK.cmd")
    assert "use VERIFY_CLIFF_PACK.cmd from the project root" in wrapper_text
    assert "Readiness pack verification passed" in wrapper_text
    assert "frank-create-cliff-readiness-latest.zip" in wrapper_text
    assert "Get-FileHash -LiteralPath $PackPath -Algorithm SHA256" in script_text
    assert "checksum mismatch" in script_text
    assert "OPEN_ME_FIRST.md" in script_text
    assert "Read-ZipBytes" in script_text
    assert 'sync/frank-create-sync-manifest-latest.json' in script_text
    assert "frank-create.sync.v1" in script_text
    assert "FrankHub sync manifest" in script_text
    assert "frank-create-handoff.json" in script_text
    assert "HANDOFF_SPEC.md" in script_text
    assert "Nested Cliff handoff ZIP is missing HANDOFF_SPEC.md." in script_text
    assert "Nested Cliff handoff manifest is missing approved workflow provenance." in script_text
    assert "Nested Cliff handoff ZIP is missing approved workflow sidecar JSON files." in script_text
    assert "Nested Cliff handoff manifest is missing approved workflow_sidecar_path." in script_text
    assert "workflow_bridge" in script_text
    assert "Nested Cliff handoff workflow sidecar is missing workflow bridge metadata." in script_text
    assert "Nested Cliff handoff workflow bridge metadata is incomplete." in script_text
    assert "Nested Cliff handoff manifest is missing channel export metadata." in script_text
    assert "Nested Cliff handoff ZIP is missing channel export image" in script_text
    assert "Nested Cliff handoff channel export integrity mismatch." in script_text
    assert "Test-HandoffManifestMediaIntegrity" in script_text
    assert "ComputeHash" in script_text
    assert "Nested Cliff handoff manifest is missing $Label media_integrity." in script_text
    assert "Nested Cliff handoff manifest has $Label media integrity mismatch." in script_text
    assert "Nested Cliff handoff ZIP is missing $Label media file" in script_text
    assert 'Read-ZipText -Archive $archive -EntryName "launchers/CLIFF_START_HERE.cmd"' in script_text
    assert "$packContextLaunchers = @(" in script_text
    assert 'Read-ZipText -Archive $archive -EntryName "launchers/$launcherName"' in script_text
    assert "Packaged CLIFF_START_HERE.cmd does not open the latest demo evidence receipt." in script_text
    assert "Packaged CLIFF_START_HERE.cmd does not detect extracted readiness-pack context." in script_text
    assert "Packaged CLIFF_START_HERE.cmd does not explain extracted-pack proof-doc mode." in script_text
    assert "Packaged $launcherName does not guard extracted readiness-pack context." in script_text
    for launcher_name in (
        "CLIFF_START_HERE.cmd",
        "START_FRANK_CREATE_DEMO.cmd",
        "START_FRANK_CREATE.cmd",
        "CHECK_FRANK_CREATE.cmd",
        "VERIFY_CLIFF_PACK.cmd",
        "PREP_FRANK_CREATE_FOR_CLIFF.cmd",
        "BUILD_FRANK_CREATE_READINESS_PACK.cmd",
        "STOP_FRANK_CREATE.cmd",
    ):
        assert launcher_name in script_text
    assert "Packaged CLIFF_START_HERE.cmd does not open the implementation manifest." in script_text
    assert "Packaged CLIFF_START_HERE.cmd does not open the latest call brief." in script_text
    assert "Packaged CLIFF_START_HERE.cmd does not open the provider-readiness receipt." in script_text
    assert "Packaged CLIFF_START_HERE.cmd does not open the activation checklist." in script_text
    assert "Packaged CLIFF_START_HERE.cmd does not open the brand-context receipt." in script_text
    assert "IMPLEMENTATION_MANIFEST.md" in script_text
    assert "Frank Create Implementation Manifest" in script_text
    builder_text = (ROOT / "scripts" / "Build-FrankCreateReadinessPack.ps1").read_text(encoding="utf-8")
    assert "starts or reuses the local Studio, runs the call-day chain" in builder_text
    assert "Google Gemini/Nano Banana is the first live API path" in builder_text
    assert "Implementation manifest does not prove the visible Studio mask-save browser QA path." in script_text
    assert "Implementation manifest does not prove browser QA mask cleanup." in script_text
    assert "Implementation manifest does not prove the no-spend adapter audit" in script_text
    assert "Provider Setup key fields are limited to Gemini, OpenAI, and Replicate" in script_text
    assert "Readiness pack Browser QA receipt is missing Provider Setup launch-order proof." in script_text
    assert "Provider readiness receipt is missing operation request preview proof." in script_text
    assert "OPEN_FOR_CLIFF.md" in script_text
    assert "OPEN_FOR_CLIFF.md does not summarize the browser QA mask-save proof." in script_text
    assert "OPEN_FOR_CLIFF.md does not mention browser QA mask cleanup." in script_text
    assert "OPEN_FOR_CLIFF.md does not summarize the browser QA run-brief copy proof." in script_text
    assert "OPEN_FOR_CLIFF.md does not summarize the Provider Setup launch-order proof." in script_text
    assert "OPEN_FOR_CLIFF.md does not summarize the selected-model preflight proof." in script_text
    assert "OPEN_FOR_CLIFF.md does not summarize the local Generate proof." in script_text
    assert "OPEN_FOR_CLIFF.md does not summarize the masked-edit Generate proof." in script_text
    assert "FRANK_CREATE_CALL_DAY.md does not include the selective-retouch and run-brief browser QA talk track." in script_text
    assert "FRANK_CREATE_CALL_DAY.md does not include the Provider Setup three-provider talk track." in script_text
    assert "FRANK_CREATE_CALL_DAY.md does not include the selected-model preflight talk track." in script_text
    assert "FRANK_CREATE_CALL_DAY.md does not include the local Generate and masked-edit Generate proof talk track." in script_text
    assert "FRANK_CREATE_DEMO.md does not describe the visible Studio browser QA proof." in script_text
    assert "FRANK_CREATE_DEMO.md does not describe the Provider Setup three-provider proof." in script_text
    assert "FRANK_CREATE_DEMO.md does not list all Cliff pack provider env vars." in script_text
    assert "FRANK_CREATE_DEMO.md does not describe the selected-output run-brief proof." in script_text
    assert "Implementation manifest does not prove the visible Studio run-brief copy path." in script_text
    assert "launchers/VERIFY_CLIFF_PACK.cmd" in script_text
    assert "qa/shareable-pack-hygiene.json" in script_text
    assert "provider-readiness/frank-create-provider-readiness-latest.md" in script_text
    assert "activation-checklist/frank-create-activation-checklist-latest.md" in script_text
    assert "brand-context/frank-create-brand-context-latest.md" in script_text
    assert "provider_audit" in script_text
    assert "Provider Adapter Audit screenshot" in script_text
    assert "No-Spend Adapter Audit" in script_text
    assert "Adapter runners registered" in script_text
    assert "External API calls made" in script_text
    assert "Secret values returned" in script_text
    assert "receipts/cliff_prep_status.json" in script_text
    assert "provider_adapter_audit" in script_text
    assert "Cliff prep provider audit" in script_text
    assert "Provider template contains a provider-token-shaped value" in script_text
    assert "Provider template is missing launch provider key placeholder: $envVar" in script_text
    assert "visible UI checksum at browser-QA time" in script_text
    assert "readiness ZIP .sha256 sidecar" in script_text
    for env_var in (
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "REPLICATE_API_TOKEN",
    ):
        assert env_var in script_text
    assert "Activation checklist receipt is missing the exposed Replicate token rotation step." in script_text
    assert "Activation checklist JSON does not include the production unlock steps." in script_text
    assert "Write-Step \"Readiness pack verified" in script_text


def test_demo_preflight_script_checks_doctor_endpoint():
    script = ROOT / "scripts" / "Test-FrankCreateDemo.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "/api/frank/health" in text
    assert "/api/frank/demo-doctor" in text
    assert "readyForDemo" in text
    assert "Start-FrankCreate.ps1" in text


def test_workflow_smoke_wrapper_runs_python_workflow_check():
    script = ROOT / "scripts" / "Test-FrankCreateWorkflow.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "frank_workflow_smoke.py" in text
    assert "Start-FrankCreate.ps1" in text
    assert "--base-url" in text
    assert "http://127.0.0.1" in text


def test_cliff_prep_wrapper_runs_full_demo_readiness_chain():
    script = ROOT / "scripts" / "Test-FrankCreateCliffPrep.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "Test-FrankCreateWorkflow.ps1" in text
    assert "Test-FrankCreateDemo.ps1" in text
    assert "Test-FrankCreateEvidence.ps1" in text
    assert "Start-FrankCreate.ps1" in text
    assert "ResetDemoData" in text
    assert "$FrankApi/demo/call-brief" in text
    assert "Write-CallBrief" in text
    assert "Get-LatestCallBriefFiles" in text
    assert "frank-create-call-brief-latest.md" in text
    assert "call_brief" in text
    assert "cliff_prep_status.json" in text
    assert "Write-CliffPrepReceipt" in text
    assert text.count("Write-CliffPrepReceipt") >= 3
    assert '$FrankApi/sessions' in text
    assert '$FrankApi/demo-doctor' in text
    assert '$FrankApi/provider-audit' in text
    assert "Test-ProviderAdapterAudit" in text
    assert "Provider audit OK" in text
    assert "provider_adapter_audit" in text
    assert "secret_values_returned" in text
    assert "/handoff" in text
    assert "frank-create-handoff.json" in text
    assert "README.md" in text
    assert "Cliff prep complete" in text


def test_readiness_pack_script_bundles_latest_proof_without_secrets():
    script = ROOT / "scripts" / "Build-FrankCreateReadinessPack.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "Test-FrankCreateCliffPrep.ps1" in text
    assert "SkipPrep" in text
    assert "Refreshing latest evidence receipt" in text
    assert "$FrankApi/demo/evidence" in text
    assert "frank-create-demo-evidence-latest.md" in text
    assert "frank-create-demo-evidence-latest.json" in text
    assert "FrankUserDir" in text
    assert "$LauncherFiles" in text
    assert "launchers\\$launcherFile" in text
    assert "ProviderEnvExamplePath" in text
    assert "setup\\frank-create.env.example" in text
    assert "setup/frank-create.env.example" in text
    assert "Invoke-ReadinessScreenshotCapture" in text
    assert "playwright screenshot" in text
    assert "Advanced Graph mobile" in text
    assert "Provider Adapter Audit" in text
    assert "provider_audit=1" in text
    assert "Write-ScreenshotCaptureReceipt" in text
    assert "screenshot-capture-receipt.json" in text
    assert "screenshot-capture-receipt.md" in text
    assert "screenshot_capture" in text
    assert "Copy-ReadinessScreenshots" in text
    assert "studio-live-mobile-latest.png" in text
    assert "provider-audit-live-desktop-latest.png" in text
    assert "graph-live-desktop-latest.png" in text
    assert "graph-live-mobile-latest.png" in text
    assert "New-BrowserQaReceipt" in text
    assert "Write-BrowserQaReceipt" in text
    assert "Update-StagedCliffPrepBrowserQa" in text
    assert "browser-qa-receipt.json" in text
    assert "browser-qa-receipt.md" in text
    assert "studio_interactions" in text
    assert "studioInteractionProof" in text
    assert "New-ShareablePackHygieneReceipt" in text
    assert "Write-ShareablePackHygieneReceipt" in text
    assert "shareable-pack-hygiene.json" in text
    assert "shareable-pack-hygiene.md" in text
    assert "Readiness pack hygiene check failed" in text
    assert "provider-token-shaped value" in text
    assert "studio-live-desktop-latest.png" in text
    assert "raw-comfy-live-quiet-latest.png" in text
    assert "workflow_smoke_status.json" in text
    assert "cliff_prep_status.json" in text
    assert "Write-ProviderReadinessReceipt" in text
    assert "$FrankApi/provider-status" in text
    assert "$FrankApi/provider-audit" in text
    assert "No-Spend Adapter Audit" in text
    assert "Adapter runners registered" in text
    assert "External API calls made" in text
    assert "Secret values returned" in text
    assert "Mocked Live-Path Coverage" in text
    assert "server-side Replicate token path" in text
    assert "DestinationDir $EvidenceDir" in text
    assert "frank-create-provider-readiness-latest.json" in text
    assert "provider-readiness/frank-create-provider-readiness-latest.md" in text
    assert "activation-checklist/frank-create-activation-checklist-latest.md" in text
    assert "frank-create-brand-context-latest.json" in text
    assert "brand-context/frank-create-brand-context-latest.md" in text
    assert "Frank Create Provider Readiness" in text
    assert "Frank Create Production Unlock Checklist" in text
    assert "Write-ActivationChecklistReceipt" in text
    assert "$FrankApi/activation-checklist" in text
    assert "Paste rotated live provider keys" in text
    assert "Rotate the exposed Replicate token" in text
    assert "FRANK_CREATE_CALL_DAY.md" in text
    assert "FRANK_CREATE_DEMO.md" in text
    assert "OPEN_FOR_CLIFF.md" in text
    assert "setup/frank-create.env.example" in text
    assert "launchers/CLIFF_START_HERE.cmd" in text
    assert "launchers/START_FRANK_CREATE_DEMO.cmd" in text
    assert "launchers/START_FRANK_CREATE.cmd" in text
    assert "launchers/CHECK_FRANK_CREATE.cmd" in text
    assert "launchers/VERIFY_CLIFF_PACK.cmd" in text
    assert "launchers/PREP_FRANK_CREATE_FOR_CLIFF.cmd" in text
    assert "launchers/BUILD_FRANK_CREATE_READINESS_PACK.cmd" in text
    assert "launchers/STOP_FRANK_CREATE.cmd" in text
    assert "Add-CliffHandoffToStage" in text
    assert "Test-CliffHandoffZip" in text
    assert "Test-ReadinessPackZip" in text
    assert "Write-ReadinessPackChecksum" in text
    assert "function New-ReadinessZip" in text
    assert "CreateEntryFromFile" in text
    assert 'Replace("\\", "/")' in text
    assert "Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256" in text
    assert "Latest SHA-256" in text
    assert "$ZipPath.sha256" in text
    assert "Readiness pack ZIP is missing $name." in text
    assert "Readiness pack manifest does not list $name." in text
    assert "OPEN_ME_FIRST.md" in text
    assert "IMPLEMENTATION_MANIFEST.md" in text
    assert "Frank Create Implementation Manifest" in text
    assert "Implementation manifest with built surfaces, launch commands, and verification snapshot." in text
    assert "Workflow smoke channel exports" in text
    assert "channel exports: $($summary.workflow_smoke_channel_exports)." in text
    assert "No-spend adapter audit" in text
    assert "This is the Frank Create Cliff readiness pack." in text
    assert "The local Frank Create workflow runs end to end" in text
    assert "blank placeholder values only" in text
    assert "Provider template is missing launch provider key placeholder: $envVar" in text
    for env_var in (
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "REPLICATE_API_TOKEN",
    ):
        assert env_var in text
    assert "Readiness pack ZIP is missing the nested Cliff handoff ZIP." in text
    assert "Readiness pack Browser QA receipt is not ready." in text
    assert "Provider Setup key fields are limited to Gemini, OpenAI, and Replicate" in text
    assert "Readiness pack Browser QA receipt is missing Provider Setup launch-order proof." in text
    assert "Readiness pack provider readiness receipt is missing operation request preview proof." in text
    assert "Readiness pack hygiene receipt is not clean." in text
    assert "frank-create-handoff.json" in text
    assert "Cliff handoff ZIP has no channel export files." in text
    assert "Cliff handoff manifest has missing channel export metadata." in text
    assert "Cliff handoff channel export has missing media integrity metadata." in text
    assert "media_integrity" in text
    assert "missing approved media integrity metadata" in text
    assert "workflow_provenance" in text
    assert "missing approved workflow provenance" in text
    assert "workflow provenance, channel-ready approved-image exports, media integrity metadata" in text
    assert "byte-for-byte media integrity" in text
    assert "compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata" in text
    assert "approved/*" in text
    assert "references/*" in text
    assert "/handoff" in text
    assert "handoffs/" in text
    assert "cliff_pack" in text
    assert "approved_asset_count" in text
    assert "readiness-pack-manifest.json" in text
    assert "No provider secrets are included" in text
    assert "The call-day handoff copy is frank-create-cliff-readiness-latest.zip" in text
    assert "OPEN_FOR_CLIFF.md is the shortest workstation note" in text
    assert "Call-day file: frank-create-cliff-readiness-latest.zip." in text
    assert "Command Roster" in text
    assert "CLIFF_START_HERE.cmd" in text
    assert "START_FRANK_CREATE_DEMO.cmd" in text
    assert "CHECK_FRANK_CREATE.cmd" in text
    assert "VERIFY_CLIFF_PACK.cmd" in text
    assert "BUILD_FRANK_CREATE_READINESS_PACK.cmd" in text
    assert "STOP_FRANK_CREATE.cmd" in text
    assert "call-brief/frank-create-call-brief-latest.md" in text
    assert "Latest one-page Cliff call brief Markdown and JSON" in text
    assert "Latest provider-readiness Markdown and JSON" in text
    assert "Latest production activation checklist Markdown and JSON" in text
    assert "Latest brand-context Markdown and JSON" in text
    assert "One-page call-day checklist" in text
    assert "Blank provider-key template under setup/" in text
    assert "Short OPEN_FOR_CLIFF note" in text
    assert "Local launcher wrappers under launchers/" in text
    assert "Eight current QA screenshots" in text
    assert "Video Lab" in text
    assert "Provider Adapter Audit" in text
    assert "handoff-review/frank-create-review-board-latest.png" in text
    assert "nested handoffs/ ZIP" in text
    assert "New-ReadinessZip -SourceDir $stageDir -ZipPath $zipPath" in text
    assert "Verify-FrankCreateReadinessPack.ps1" in text
    assert "Running strict readiness pack verifier" in text
    assert "Strict readiness pack verifier failed" in text
    assert "Latest readiness pack" in text
    assert "Checksum sidecar: frank-create-cliff-readiness-latest.zip.sha256." in text
    assert "SHA-256 sidecar for the top-level readiness ZIP" in text
    assert "Acceptance Matrix" in text
    assert "Conversational Image Studio" in text
    assert "Product Shot Lab flow" in text
    assert "Generate, edit, approve, export" in text
    assert "Video Lab storyboard" in text
    assert "Advanced Graph + raw Comfy" in text
    assert "Frank Body Mode + brand context" in text
    assert "Brand-context brief packaged with" in text
    assert "Live provider adapters" in text
    assert "Production activation checklist" in text
    assert "Server-side key hygiene" in text
    assert "Cliff handoff integrity" in text
    assert "provider_keys.env" not in text


def test_demo_runbook_has_cliff_ready_flow():
    runbook = ROOT / "FRANK_CREATE_DEMO.md"

    assert runbook.exists()
    text = runbook.read_text(encoding="utf-8")

    assert "START_FRANK_CREATE.cmd" in text
    assert "CLIFF_START_HERE.cmd" in text
    assert "OPEN_FOR_CLIFF.md" in text
    assert "STOP_FRANK_CREATE.cmd" in text
    assert "CHECK_FRANK_CREATE.cmd" in text
    assert "VERIFY_CLIFF_PACK.cmd" in text
    assert "PREP_FRANK_CREATE_FOR_CLIFF.cmd" in text
    assert "BUILD_FRANK_CREATE_READINESS_PACK.cmd" in text
    assert "CLIFF_START_HERE.cmd" in text
    assert "Command Roster" in text
    assert "Cliff call-day start" in text
    assert "Clean demo start" in text
    assert "Fast readiness check" in text
    assert "Shareable proof pack" in text
    assert "Stop local server" in text
    assert "keeps the fallback URL visible if the browser does not open" in text
    assert "Build-FrankCreateReadinessPack.ps1 -SkipPrep" in text
    assert "frank-create-cliff-readiness-latest.zip" in text
    assert "frank-create-cliff-readiness-latest.zip.sha256" in text
    assert "proves the visible Studio path in browser QA" in text
    assert "wrapper opens the readiness folder, `frank-create-implementation-manifest-latest.md`, `frank-create-demo-evidence-latest.md`, `frank-create-call-brief-latest.md`, `frank-create-provider-readiness-latest.md`, `frank-create-activation-checklist-latest.md`, and `frank-create-brand-context-latest.md`" in text
    assert "Build call pack" in text
    assert "handoffs/" in text
    assert "readiness_packs" in text
    assert "http://127.0.0.1:8190" in text
    assert "provider_keys.env" in text
    assert "Save server keys" in text
    assert "Provider Setup" in text
    assert "input clears after save" in text
    for env_var in (
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "REPLICATE_API_TOKEN",
    ):
        assert f"$env:{env_var}" in text
    assert "Never put real keys into chat, docs, source files, screenshots, or exported packs" in text
    assert "three-provider Cliff launch plan" in text
    assert "-ResetDemoData" in text
    assert "Rotate the exposed Replicate token" in text
    assert "Advanced Graph" in text
    assert "Prepare model folders" in text
    assert "full local diffusion" in text
    assert "call-day Cliff demo" in text
    assert "Cliff Call-Day Proof" in text
    assert "frank-create-demo-evidence-latest.md" in text
    assert "frank-create-call-brief-latest.md" in text
    assert "Ready for demo: yes" in text
    assert "Launch Model Roster" in text
    assert "no-spend adapter audit" in text
    assert "5 / 5" in text
    assert "Live video stays out of the Cliff pack" in text
    assert "Test-FrankCreateDemo.ps1" in text
    assert "Test-FrankCreateWorkflow.ps1" in text
    assert "Test-FrankCreateCliffPrep.ps1" in text


def test_call_day_checklist_has_fast_cliff_operator_flow():
    checklist = ROOT / "FRANK_CREATE_CALL_DAY.md"

    assert checklist.exists()
    text = checklist.read_text(encoding="utf-8")

    assert "START_FRANK_CREATE_DEMO.cmd" in text
    assert "CLIFF_START_HERE.cmd" in text
    assert "OPEN_FOR_CLIFF.md" in text
    assert "STOP_FRANK_CREATE.cmd" in text
    assert "CHECK_FRANK_CREATE.cmd" in text
    assert "VERIFY_CLIFF_PACK.cmd" in text
    assert "http://127.0.0.1:8190" in text
    assert "Command Roster" in text
    assert "Cliff call-day start" in text
    assert "Clean demo start" in text
    assert "Fast readiness check" in text
    assert "Shareable proof pack" in text
    assert "Stop local server" in text
    assert "launcher keeps this fallback URL visible" in text
    assert "ready_with_warnings" in text
    assert "BUILD_FRANK_CREATE_READINESS_PACK.cmd" in text
    assert "frank-create-cliff-readiness-latest.zip" in text
    assert "frank-create-cliff-readiness-latest.zip.sha256" in text
    assert "opens the readiness folder, implementation manifest, evidence receipt, one-page call brief, provider-readiness receipt, activation checklist, and brand-context brief" in text
    assert "Product Shot Lab" in text
    assert "Video Lab" in text
    assert "Advanced Graph" in text
    assert "Prepare model folders" in text
    assert "checkpoints" in text
    assert "Provider keys stay server-side" in text
    assert "byte-for-byte media integrity" in text
    assert "compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata" in text
    assert "mask painter save" in text
    assert "Check selected model" in text
    assert "no-spend selected model preflight" in text
    assert "local Studio Generate button" in text
    assert "masked edit Generate button" in text
    assert "Paint edit mask" in text
    assert "Provider Setup" in text
    assert "never into chat, docs, source, screenshots, or exported packs" in text
    assert "Gemini, OpenAI, and Replicate" in text
    assert "Rotate the exposed Replicate token" in text
    assert "tomorrow" not in text.lower()


def test_open_for_cliff_names_browser_qa_interaction_proof():
    note = ROOT / "OPEN_FOR_CLIFF.md"

    assert note.exists()
    text = note.read_text(encoding="utf-8")

    assert "browser QA receipt" in text
    assert "provider key plan" in text
    assert "safe provider key plan" in text
    assert "no-spend selected model preflight" in text
    assert "local Studio Generate button" in text
    assert "masked edit Generate button" in text
    assert "Gemini, OpenAI, and Replicate" in text
    assert "env-var names" in text
    assert "Open review board" in text
    assert "direct visual review-board PNG" in text
    assert "Open sync manifest" in text
    assert "frank-create.sync.v1" in text
    assert "handoff-review/frank-create-review-board-latest.png" in text
    assert "painted mask saves into the `Masked Edit` composer" in text
    assert "QA-created mask assets and files are cleaned up afterward" in text
    assert "byte-for-byte media integrity" in text
    assert "compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata" in text


def test_browser_qa_proves_provider_setup_three_provider_boundary():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "providerKeyFields" in text
    assert "GOOGLE_API_KEY" in text
    assert "REPLICATE_API_TOKEN" in text
    assert "OPENAI_API_KEY" in text
    assert "Provider Setup key fields were not limited to the Cliff pack providers" in text
    assert "hasOpenAiKey" in text


def test_browser_qa_proves_safe_production_unlock_plan_copy():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"
    verifier = ROOT / "scripts" / "Verify-FrankCreateReadinessPack.ps1"

    assert script.exists()
    assert verifier.exists()
    text = script.read_text(encoding="utf-8")
    verifier_text = verifier.read_text(encoding="utf-8")

    assert "__frankCopiedProductionUnlockPlan" in text
    assert "Copy unlock plan" in text
    assert "Frank Create Production Unlock Plan" in text
    assert "hasCheckpointPath" in text
    assert "hasNoSecretShape" in text
    assert "safe production unlock plan" in text
    assert "Readiness pack Browser QA receipt is missing production unlock copy proof." in verifier_text


def test_browser_qa_proves_no_spend_selected_model_preflight():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"
    verifier = ROOT / "scripts" / "Verify-FrankCreateReadinessPack.ps1"

    assert script.exists()
    assert verifier.exists()
    text = script.read_text(encoding="utf-8")
    verifier_text = verifier.read_text(encoding="utf-8")

    assert "__frankSelectedModelPreflightProof" in text
    assert "const hasNoSecretShape" in text
    assert "document.querySelector('.provider-preflight-card')" in text
    assert "secretPattern.test(cardText + ' ' + statusText) === false" in text
    assert "Check selected model" in text
    assert "Selected model preflight" in text
    assert 'key = "studio_model_preflight"' in text
    assert "no-spend selected model preflight" in text
    assert "Readiness pack Browser QA receipt is missing selected model preflight proof." in verifier_text


def test_browser_qa_proves_live_local_generate_button_path():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"
    verifier = ROOT / "scripts" / "Verify-FrankCreateReadinessPack.ps1"

    assert script.exists()
    assert verifier.exists()
    text = script.read_text(encoding="utf-8")
    verifier_text = verifier.read_text(encoding="utf-8")

    assert "__frankGenerateProof" in text
    assert "Browser QA local generate proof" in text
    assert "outputCountAfter" in text
    assert 'key = "studio_local_generate"' in text
    assert "local Studio Generate button created output assets" in text
    assert "Readiness pack Browser QA receipt is missing local generate button proof." in verifier_text


def test_browser_qa_proves_live_masked_edit_button_path():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"
    verifier = ROOT / "scripts" / "Verify-FrankCreateReadinessPack.ps1"

    assert script.exists()
    assert verifier.exists()
    text = script.read_text(encoding="utf-8")
    verifier_text = verifier.read_text(encoding="utf-8")

    assert "__frankMaskedEditProof" in text
    assert "Browser QA masked edit proof" in text
    assert "maskedOutputCountAfter" in text
    assert "maskedOutputCountAfter = maskedOutputCountBefore;\n  let statusText = '';\n  for (let attempt = 0; attempt < 180" in text
    assert 'key = "studio_masked_edit_generate"' in text
    assert "masked edit Generate button created output assets" in text
    assert "Readiness pack Browser QA receipt is missing masked edit button proof." in verifier_text


def test_browser_qa_proves_raw_comfy_canvas_is_lightly_branded_and_unblocked():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "blockingOverlayIds" in text
    assert "frank-comfy-brand-chrome" in text
    assert "frank-comfy-production-plate" in text
    assert "highZBlockers" in text
    assert "rawComfyHasCanvas" in text
    assert "raw Comfy canvas is lightly branded and unobstructed" in text


def test_browser_qa_proves_workflow_map_stage_interaction():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "Workflow Map" in text
    assert "Real\\s+node\\s+graph\\s+lives\\s+in\\s+Comfy\\s+Canvas\\." in text
    assert "Selected stage 04" in text
    assert "Inspect Make Magic" in text
    assert "Inspect The Brief" in text
    assert "Selected stage 01" in text
    assert "Advanced Graph stage click did not update the inspector" in text
    assert "clickable stage inspector updates" in text


def test_readiness_pack_builder_can_reuse_existing_screenshots():
    script = ROOT / "scripts" / "Build-FrankCreateReadinessPack.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "[switch]$SkipScreenshotRefresh" in text
    assert "Screenshot refresh skipped; existing QA screenshots will be reused." in text
    assert "Screenshot refresh was skipped by request; existing QA screenshots were reused." in text
    assert "-SkipRefresh:$SkipScreenshotRefresh" in text


def test_readiness_pack_builder_clears_stale_verifier_exit_code():
    script = ROOT / "scripts" / "Build-FrankCreateReadinessPack.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "$global:LASTEXITCODE = 0" in text
    assert "if (!$? -or $LASTEXITCODE -ne 0)" in text


def test_browser_qa_proves_provider_audit_operation_previews():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"

    assert script.exists()
    text = script.read_text(encoding="utf-8")

    assert "operation previews checked" in text
    assert "Provider Adapter Audit did not show operation request preview coverage." in text


def test_browser_qa_proves_visible_demo_doctor_readiness_pack_sha():
    script = ROOT / "scripts" / "Test-FrankCreateBrowserQa.ps1"
    verifier = ROOT / "scripts" / "Verify-FrankCreateReadinessPack.ps1"

    assert script.exists()
    assert verifier.exists()
    text = script.read_text(encoding="utf-8")
    verifier_text = verifier.read_text(encoding="utf-8")

    assert "readinessPackSha" in text
    assert "Verified SHA-256" in text
    assert "replace(/SHA-256/gi" in text
    assert "Demo Doctor visible checksum proof failed" in text
    assert 'key = "demo_doctor_checksum"' in text
    assert "Demo Doctor readiness pack checksum" in text
    assert "Readiness pack Browser QA receipt is missing Demo Doctor checksum proof." in verifier_text
