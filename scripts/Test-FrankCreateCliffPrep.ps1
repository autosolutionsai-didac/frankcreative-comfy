param(
    [int]$Port = 8190,
    [switch]$ResetDemoData
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Launcher = Join-Path $Root "scripts\Start-FrankCreate.ps1"
$WorkflowCheck = Join-Path $Root "scripts\Test-FrankCreateWorkflow.ps1"
$DoctorCheck = Join-Path $Root "scripts\Test-FrankCreateDemo.ps1"
$EvidenceCheck = Join-Path $Root "scripts\Test-FrankCreateEvidence.ps1"
$BrowserQaCheck = Join-Path $Root "scripts\Test-FrankCreateBrowserQa.ps1"
$PrepStatusPath = Join-Path $Root "user\frank_create\cliff_prep_status.json"
$WorkflowStatusPath = Join-Path $Root "user\frank_create\workflow_smoke_status.json"
$BrowserQaStatusPath = Join-Path $Root "user\frank_create\browser_qa_status.json"
$EvidenceDir = Join-Path $Root "user\frank_create\demo_evidence"
$BaseUrl = "http://127.0.0.1:$Port"
$FrankApi = "$BaseUrl/api/frank"
$Script:CliffPackReceipt = $null
$Script:ProviderAuditReceipt = $null
$Script:BrowserQaReceipt = $null

function Write-Step {
    param([string]$Message, [string]$Color = "Magenta")
    Write-Host "[Frank Cliff Prep] $Message" -ForegroundColor $Color
}

function Assert-LastExitCode {
    param([string]$StepName)
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $StepName"
    }
}

function Invoke-Json {
    param(
        [string]$Uri,
        [string]$Method = "GET",
        [object]$Body = $null
    )

    if ($Body -ne $null) {
        return Invoke-RestMethod -Uri $Uri -Method $Method -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 8) -TimeoutSec 30
    }

    return Invoke-RestMethod -Uri $Uri -Method $Method -TimeoutSec 30
}

function Test-SeededCliffPack {
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $sessions = (Invoke-Json "$FrankApi/sessions").sessions
    $session = $sessions | Where-Object { $_.name -eq "Frank Body Demo Studio" -and $_.status -eq "active" } | Select-Object -First 1
    if (!$session) {
        throw "Frank Body Demo Studio session was not found."
    }

    $handoff = Invoke-Json "$FrankApi/sessions/$($session.id)/handoff" "POST" @{ summary = "Seeded Frank Body demo handoff for Cliff prep." }
    $downloadUrl = "$BaseUrl$($handoff.download_url)"
    $tempZip = Join-Path ([System.IO.Path]::GetTempPath()) "frank-create-cliff-pack-$([Guid]::NewGuid().ToString('N')).zip"
    Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $tempZip -TimeoutSec 45

    $archive = [System.IO.Compression.ZipFile]::OpenRead($tempZip)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName })
        if ($names -notcontains "README.md") {
            throw "Cliff Pack ZIP is missing README.md."
        }
        if ($names -notcontains "frank-create-handoff.json") {
            throw "Cliff Pack ZIP is missing frank-create-handoff.json."
        }

        $manifestEntry = $archive.GetEntry("frank-create-handoff.json")
        $reader = New-Object System.IO.StreamReader($manifestEntry.Open())
        try {
            $manifest = $reader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $reader.Dispose()
        }

        $approvedCount = @($manifest.approved_assets).Count
        $referenceCount = @($manifest.reference_assets).Count
        if ($approvedCount -lt 1) {
            throw "Cliff Pack manifest has no approved assets."
        }
        if ($referenceCount -lt 1) {
            throw "Cliff Pack manifest has no reference assets."
        }

        $Script:CliffPackReceipt = [ordered]@{
            export_id = $handoff.handoff.id
            download_url = $handoff.download_url
            approved_asset_count = $approvedCount
            reference_asset_count = $referenceCount
            archive_file_count = @($archive.Entries).Count
            has_readme = $true
            has_manifest = $true
        }
        Write-Step "Cliff Pack OK: $approvedCount approved, $referenceCount reference, export $($handoff.handoff.id)" "Green"
    } finally {
        $archive.Dispose()
        Remove-Item -LiteralPath $tempZip -Force -ErrorAction SilentlyContinue
    }
}

function Test-ProviderAdapterAudit {
    $audit = Invoke-Json "$FrankApi/provider-audit"
    $summary = $audit.summary
    $runnerCount = [int]$summary.runner_registered
    $modelCount = [int]$summary.model_count
    $missingRunners = [int]$summary.missing_runners
    $previewFailures = [int]$summary.preview_failures

    if ($modelCount -lt 1) {
        throw "Provider adapter audit returned no launch models."
    }
    if ($runnerCount -ne $modelCount -or $missingRunners -ne 0) {
        throw "Provider adapter audit found missing launch runners: $runnerCount / $modelCount registered, $missingRunners missing."
    }
    if ($previewFailures -ne 0) {
        throw "Provider adapter audit found $previewFailures request-preview failure(s)."
    }
    if (-not [bool]$summary.no_spend) {
        throw "Provider adapter audit did not confirm no-spend mode."
    }
    if ([bool]$summary.secret_values_returned) {
        throw "Provider adapter audit reported secret values in the response."
    }

    $Script:ProviderAuditReceipt = [ordered]@{
        model_count = $modelCount
        runner_registered = $runnerCount
        missing_runners = $missingRunners
        ready_models = [int]$summary.ready_models
        waiting_for_key = [int]$summary.waiting_for_key
        preview_failures = $previewFailures
        no_spend = [bool]$summary.no_spend
        secret_values_returned = [bool]$summary.secret_values_returned
    }
    Write-Step "Provider audit OK: $runnerCount / $modelCount launch runners, $previewFailures preview failures" "Green"
}

function Test-BrowserQa {
    & $BrowserQaCheck -BaseUrl $BaseUrl -StatusPath $BrowserQaStatusPath
    Assert-LastExitCode "browser QA"
    if (!(Test-Path -LiteralPath $BrowserQaStatusPath)) {
        throw "Browser QA did not write a status receipt."
    }
    $status = Get-Content -LiteralPath $BrowserQaStatusPath -Raw | ConvertFrom-Json
    if ($status.status -ne "ready") {
        throw "Browser QA did not report ready status."
    }
    $readyChecks = @($status.checks | Where-Object { $_.status -eq "ready" }).Count
    if ($readyChecks -lt 3) {
        throw "Browser QA reported too few ready checks: $readyChecks"
    }
    $Script:BrowserQaReceipt = $status
    Write-Step "Browser QA OK: $readyChecks rendered surfaces checked" "Green"
}

function Read-JsonFileOrNull {
    param([string]$Path)
    if (!(Test-Path $Path)) {
        return $null
    }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Get-LatestEvidenceFiles {
    if (!(Test-Path $EvidenceDir)) {
        return @{}
    }

    $latestMarkdown = Get-ChildItem -LiteralPath $EvidenceDir -Filter "frank-create-demo-evidence-*.md" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $latestJson = Get-ChildItem -LiteralPath $EvidenceDir -Filter "frank-create-demo-evidence-*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    return @{
        markdown_path = $(if ($latestMarkdown) { $latestMarkdown.FullName } else { $null })
        json_path = $(if ($latestJson) { $latestJson.FullName } else { $null })
    }
}

function Get-LatestCallBriefFiles {
    if (!(Test-Path $EvidenceDir)) {
        return @{}
    }

    $latestMarkdown = Join-Path $EvidenceDir "frank-create-call-brief-latest.md"
    $latestJson = Join-Path $EvidenceDir "frank-create-call-brief-latest.json"
    return @{
        markdown_path = $(if (Test-Path -LiteralPath $latestMarkdown) { $latestMarkdown } else { $null })
        json_path = $(if (Test-Path -LiteralPath $latestJson) { $latestJson } else { $null })
    }
}

function Write-CallBrief {
    $brief = Invoke-Json "$FrankApi/demo/call-brief" "POST" @{ base_url = $BaseUrl }
    if (!$brief.latest_markdown_path -or !(Test-Path -LiteralPath $brief.latest_markdown_path)) {
        throw "Call brief Markdown was not created."
    }
    if (!$brief.latest_json_path -or !(Test-Path -LiteralPath $brief.latest_json_path)) {
        throw "Call brief JSON was not created."
    }
    Write-Step "Call brief: $($brief.latest_markdown_path)" "Green"
}

function Write-CliffPrepReceipt {
    $doctor = Invoke-Json "$FrankApi/demo-doctor"
    $workflowSmoke = Read-JsonFileOrNull $WorkflowStatusPath
    $evidenceFiles = Get-LatestEvidenceFiles
    $callBriefFiles = Get-LatestCallBriefFiles
    $receipt = [ordered]@{
        ok = $true
        completed_at = [DateTimeOffset]::UtcNow.ToString("o")
        base_url = $BaseUrl
        doctor = [ordered]@{
            status = $doctor.status
            ready_for_demo = [bool]$doctor.readyForDemo
            headline = $doctor.headline
        }
        workflow_smoke = [ordered]@{
            ok = [bool]$workflowSmoke.ok
            session_name = $workflowSmoke.session_name
            completed_at = $workflowSmoke.completed_at
            handoff_media_file_count = $workflowSmoke.handoff.media_file_count
        }
        cliff_pack = $Script:CliffPackReceipt
        provider_adapter_audit = $Script:ProviderAuditReceipt
        browser_qa = $Script:BrowserQaReceipt
        evidence = $evidenceFiles
        call_brief = $callBriefFiles
    }
    $directory = Split-Path -Parent $PrepStatusPath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $PrepStatusPath -Encoding UTF8
    Write-Step "Prep receipt: $PrepStatusPath" "Green"
}

Set-Location $Root

if ($ResetDemoData) {
    Write-Step "Resetting seeded Frank demo data..." "Yellow"
    & $Launcher -Port $Port -NoBrowser -NoBuild -ResetDemoData
    if ($LASTEXITCODE -ne 0) {
        throw "Demo reset failed."
    }
}

Write-Step "Running workflow smoke..."
& $WorkflowCheck -Port $Port -StartIfDown
Assert-LastExitCode "workflow smoke"

Write-Step "Running Demo Doctor..."
& $DoctorCheck -Port $Port -StartIfDown
Assert-LastExitCode "Demo Doctor"

Write-Step "Auditing launch provider adapters..."
Test-ProviderAdapterAudit

Write-Step "Running browser QA for branded graph and audit surfaces..."
Test-BrowserQa

Write-Step "Validating visible Cliff Pack export..."
Test-SeededCliffPack

Write-CliffPrepReceipt

Write-Step "Writing evidence report..."
& $EvidenceCheck -Port $Port -StartIfDown
Assert-LastExitCode "evidence report"

Write-Step "Writing one-page Cliff call brief..."
Write-CallBrief

Write-CliffPrepReceipt

Write-Step "Cliff prep complete. Bring the goods." "Green"
exit 0
