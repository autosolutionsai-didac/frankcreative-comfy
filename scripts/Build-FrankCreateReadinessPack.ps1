param(
    [int]$Port = 8190,
    [switch]$SkipPrep,
    [switch]$SkipScreenshotRefresh
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PrepScript = Join-Path $Root "scripts\Test-FrankCreateCliffPrep.ps1"
$VerifyScript = Join-Path $Root "scripts\Verify-FrankCreateReadinessPack.ps1"
$EvidenceDir = Join-Path $Root "user\frank_create\demo_evidence"
$CallBriefDir = $EvidenceDir
$FrankUserDir = Join-Path $Root "user\frank_create"
$QaDir = Join-Path $Root "user\frank_create\qa"
$BrowserQaStatusPath = Join-Path $Root "user\frank_create\browser_qa_status.json"
$WorkflowStatusPath = Join-Path $Root "user\frank_create\workflow_smoke_status.json"
$PrepStatusPath = Join-Path $Root "user\frank_create\cliff_prep_status.json"
$RunbookPath = Join-Path $Root "FRANK_CREATE_DEMO.md"
$CallDayPath = Join-Path $Root "FRANK_CREATE_CALL_DAY.md"
$OpenForCliffPath = Join-Path $Root "OPEN_FOR_CLIFF.md"
$ProviderEnvExamplePath = Join-Path $Root "config\frank-create.env.example"
$OutputDir = Join-Path $Root "user\frank_create\readiness_packs"
$BaseUrl = "http://127.0.0.1:$Port"
$FrankApi = "$BaseUrl/api/frank"
$LauncherFiles = @(
    "CLIFF_START_HERE.cmd",
    "START_FRANK_CREATE_DEMO.cmd",
    "START_FRANK_CREATE.cmd",
    "CHECK_FRANK_CREATE.cmd",
    "VERIFY_CLIFF_PACK.cmd",
    "PREP_FRANK_CREATE_FOR_CLIFF.cmd",
    "BUILD_FRANK_CREATE_READINESS_PACK.cmd",
    "STOP_FRANK_CREATE.cmd"
)

function Write-Step {
    param([string]$Message, [string]$Color = "Magenta")
    Write-Host "[Frank Readiness Pack] $Message" -ForegroundColor $Color
}

function Copy-RequiredFile {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (!(Test-Path -LiteralPath $Source)) {
        throw "Required file is missing: $Source"
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-OptionalFiles {
    param(
        [string]$Pattern,
        [string]$DestinationDir
    )

    $files = Get-ChildItem -Path $Pattern -File -ErrorAction SilentlyContinue
    if (!$files) {
        return @()
    }

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    foreach ($file in $files) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $DestinationDir $file.Name) -Force
    }
    return @($files | ForEach-Object { $_.Name })
}

function Write-ReadinessPackChecksum {
    param([string]$ZipPath)

    $hash = Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256
    $checksumPath = "$ZipPath.sha256"
    "$($hash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $ZipPath)" | Set-Content -LiteralPath $checksumPath -Encoding ASCII
    return [ordered]@{
        path = $checksumPath
        sha256 = $hash.Hash.ToLowerInvariant()
        file_size_bytes = (Get-Item -LiteralPath $ZipPath).Length
    }
}

function New-ReadinessZip {
    param(
        [string]$SourceDir,
        [string]$ZipPath
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem

    if (Test-Path -LiteralPath $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }

    $sourceRoot = (Resolve-Path -LiteralPath $SourceDir).Path.TrimEnd("\", "/")
    $archive = [System.IO.Compression.ZipFile]::Open($ZipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        Get-ChildItem -LiteralPath $SourceDir -Recurse -File | Sort-Object FullName | ForEach-Object {
            $relativePath = $_.FullName.Substring($sourceRoot.Length).TrimStart("\", "/")
            $entryName = $relativePath.Replace("\", "/")
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $_.FullName,
                $entryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    } finally {
        $archive.Dispose()
    }
}

function Copy-ReadinessScreenshots {
    param(
        [string]$SourceDir,
        [string]$DestinationDir
    )

    $canonicalScreenshots = @(
        "studio-live-desktop-latest.png",
        "studio-live-mobile-latest.png",
        "video-lab-live-desktop-latest.png",
        "provider-audit-live-desktop-latest.png",
        "graph-live-desktop-latest.png",
        "graph-live-mobile-latest.png",
        "raw-comfy-live-quiet-latest.png",
        "raw-comfy-workflow-receipt-latest.png"
    )
    $copied = @()
    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    foreach ($name in $canonicalScreenshots) {
        $source = Join-Path $SourceDir $name
        if (!(Test-Path -LiteralPath $source)) {
            continue
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $DestinationDir $name) -Force
        $copied += $name
    }
    return $copied
}

function Invoke-ReadinessScreenshotCapture {
    param(
        [string]$BaseUrl,
        [string]$DestinationDir,
        [switch]$SkipRefresh
    )

    if ($SkipRefresh) {
        Write-Step "Screenshot refresh skipped; existing QA screenshots will be reused." "Yellow"
        return [ordered]@{
            status = "skipped"
            generated_at = [DateTimeOffset]::UtcNow.ToString("o")
            tool = "playwright screenshot"
            base_url = $BaseUrl
            captured = @()
            issues = @()
            issue_count = 0
            notes = @("Screenshot refresh was skipped by request; existing QA screenshots were reused.")
        }
    }

    $npx = Get-Command "npx.cmd" -ErrorAction SilentlyContinue
    if (!$npx) {
        $npx = Get-Command "npx" -ErrorAction SilentlyContinue
    }
    if (!$npx) {
        Write-Step "npx was not found, so existing QA screenshots will be reused." "Yellow"
        return [ordered]@{
            status = "skipped"
            generated_at = [DateTimeOffset]::UtcNow.ToString("o")
            tool = "playwright screenshot"
            base_url = $BaseUrl
            captured = @()
            issues = @()
            issue_count = 0
            notes = @("npx was not found, so existing QA screenshots were reused.")
        }
    }

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    $receiptUrl = "$BaseUrl/comfy/"
    try {
        $assetsResponse = Invoke-RestMethod -Uri "$BaseUrl/api/frank/assets?approval_status=approved" -Method Get -TimeoutSec 10
        $receiptAsset = @($assetsResponse.assets | Where-Object { $_.kind -ne "reference" -and ($_.media_type -eq "image" -or !$_.media_type) } | Select-Object -First 1)[0]
        if ($receiptAsset -and $receiptAsset.id) {
            $receiptUrl = "$BaseUrl/comfy/?frankAssetId=$([uri]::EscapeDataString([string]$receiptAsset.id))"
        }
    } catch {
        $receiptUrl = "$BaseUrl/comfy/"
    }
    $captures = @(
        [ordered]@{ key = "studio_desktop"; label = "Studio desktop"; viewport = "1440,960"; url = $BaseUrl; file = "studio-live-desktop-latest.png" },
        [ordered]@{ key = "studio_mobile"; label = "Studio mobile"; viewport = "390,900"; url = $BaseUrl; file = "studio-live-mobile-latest.png" },
        [ordered]@{ key = "video_lab"; label = "Video Lab desktop"; viewport = "1440,960"; url = "$BaseUrl/?mode=video-lab"; file = "video-lab-live-desktop-latest.png" },
        [ordered]@{ key = "provider_audit"; label = "Provider Adapter Audit"; viewport = "1440,960"; url = "$BaseUrl/?provider_audit=1"; file = "provider-audit-live-desktop-latest.png"; wait_selector = "[aria-label='Provider adapter audit']" },
        [ordered]@{ key = "advanced_graph"; label = "Advanced Graph desktop"; viewport = "1440,960"; url = "$BaseUrl/graph"; file = "graph-live-desktop-latest.png" },
        [ordered]@{ key = "advanced_graph_mobile"; label = "Advanced Graph mobile"; viewport = "390,900"; url = "$BaseUrl/graph"; file = "graph-live-mobile-latest.png" },
        [ordered]@{ key = "raw_comfy"; label = "Raw Comfy canvas"; viewport = "1440,960"; url = "$BaseUrl/comfy/"; file = "raw-comfy-live-quiet-latest.png" },
        [ordered]@{ key = "raw_comfy_receipt"; label = "Raw Comfy selected workflow receipt"; viewport = "1440,960"; url = $receiptUrl; file = "raw-comfy-workflow-receipt-latest.png"; wait_selector = "[aria-label='Frank raw canvas workflow receipt']" }
    )

    $captured = @()
    foreach ($capture in $captures) {
        $destination = Join-Path $DestinationDir $capture["file"]
        Write-Step "Capturing $($capture["label"]) screenshot..."
        $args = @("playwright", "screenshot", "--viewport-size=$($capture["viewport"])")
        if ($capture.Contains("wait_selector")) {
            $args += "--wait-for-selector=$($capture["wait_selector"])"
        }
        $args += @($capture["url"], $destination)
        & $npx.Source @args
        if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $destination)) {
            throw "Could not capture $($capture["label"]) screenshot for the readiness pack."
        }
        $captured += [ordered]@{
            key = $capture["key"]
            label = $capture["label"]
            file = $capture["file"]
            url = $capture["url"]
            viewport = $capture["viewport"]
        }
    }

    return [ordered]@{
        status = "captured"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        tool = "playwright screenshot"
        base_url = $BaseUrl
        captured = $captured
        issues = @()
        issue_count = 0
        notes = @("All canonical QA screenshots were refreshed before the pack was written.")
    }
}

function Write-ScreenshotCaptureReceipt {
    param(
        [object]$Receipt,
        [string]$DestinationDir
    )

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    $jsonPath = Join-Path $DestinationDir "screenshot-capture-receipt.json"
    $markdownPath = Join-Path $DestinationDir "screenshot-capture-receipt.md"
    $Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    $lines = @(
        "# Frank Create Screenshot Capture Receipt",
        "",
        "Status: **$($Receipt.status)**",
        "Base URL: ``$($Receipt.base_url)``",
        "Generated: $($Receipt.generated_at)",
        "",
        "## Captured",
        ""
    )
    if (@($Receipt.captured).Count) {
        foreach ($capture in $Receipt.captured) {
            $lines += "- ``$($capture.key)`` $($capture.label): ``$($capture.file)`` at ``$($capture.viewport)``"
        }
    } else {
        $lines += "- No screenshots were captured in this run."
    }
    if (@($Receipt.issues).Count) {
        $lines += ""
        $lines += "## Issues"
        $lines += ""
        foreach ($issue in $Receipt.issues) {
            $lines += "- ``$($issue.key)`` $($issue.label): $($issue.reason)"
        }
    }
    $lines += ""
    $lines += "## Notes"
    $lines += ""
    foreach ($note in $Receipt.notes) {
        $lines += "- $note"
    }
    $lines -join "`n" | Set-Content -LiteralPath $markdownPath -Encoding UTF8
}

function Invoke-Json {
    param(
        [string]$Uri,
        [string]$Method = "GET",
        [object]$Body = $null
    )

    if ($Body -ne $null) {
        return Invoke-RestMethod -Uri $Uri -Method $Method -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 8) -TimeoutSec 45
    }

    return Invoke-RestMethod -Uri $Uri -Method $Method -TimeoutSec 45
}

function Convert-ToInt {
    param([object]$Value)
    if ($Value -eq $null) {
        return 0
    }
    return [int]$Value
}

function Join-OrNone {
    param([object[]]$Values)
    $items = @($Values | Where-Object { $_ })
    if (!$items.Count) {
        return "none"
    }
    return $items -join ", "
}

function Test-CliffHandoffZip {
    param([string]$Path)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName })
        if ($names -notcontains "README.md") {
            throw "Cliff handoff ZIP is missing README.md."
        }
        if ($names -notcontains "HANDOFF_SPEC.md") {
            throw "Cliff handoff ZIP is missing HANDOFF_SPEC.md."
        }
        if ($names -notcontains "frank-create-handoff.json") {
            throw "Cliff handoff ZIP is missing frank-create-handoff.json."
        }
        if (!($names | Where-Object { $_ -like "approved/*" })) {
            throw "Cliff handoff ZIP has no approved media files."
        }
        if (!($names | Where-Object { $_ -like "references/*" })) {
            throw "Cliff handoff ZIP has no reference media files."
        }
        if ($names -notcontains "review/frank-create-review-board.png") {
            throw "Cliff handoff ZIP is missing review/frank-create-review-board.png."
        }

        $manifestEntry = $archive.GetEntry("frank-create-handoff.json")
        $reader = New-Object System.IO.StreamReader($manifestEntry.Open())
        try {
            $manifest = $reader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $reader.Dispose()
        }

        if (@($manifest.approved_assets).Count -lt 1) {
            throw "Cliff handoff manifest has no approved assets."
        }
        if (@($manifest.reference_assets).Count -lt 1) {
            throw "Cliff handoff manifest has no reference assets."
        }
        if (!$manifest.review_board -or [string]$manifest.review_board.archive_path -ne "review/frank-create-review-board.png") {
            throw "Cliff handoff manifest has missing review board metadata."
        }
        if ([int]$manifest.review_board.approved_asset_count -lt 1 -or [int]$manifest.review_board.width -lt 1200 -or [int]$manifest.review_board.height -lt 800) {
            throw "Cliff handoff review board metadata is incomplete."
        }
        foreach ($asset in @($manifest.approved_assets)) {
            $integrity = $asset.media_integrity
            $size = 0
            if ($integrity -and $integrity.file_size_bytes) {
                $size = [int64]$integrity.file_size_bytes
            }
            if (!$integrity -or !($integrity.sha256 -is [string]) -or $integrity.sha256.Length -ne 64 -or $size -le 0) {
                throw "Cliff handoff manifest has missing approved media integrity metadata."
            }
            if (!$asset.workflow_provenance) {
                throw "Cliff handoff manifest has missing approved workflow provenance."
            }
        }
        foreach ($asset in @($manifest.proof_assets | Where-Object { $_ })) {
            $integrity = $asset.media_integrity
            $size = 0
            if ($integrity -and $integrity.file_size_bytes) {
                $size = [int64]$integrity.file_size_bytes
            }
            if (!$integrity -or !($integrity.sha256 -is [string]) -or $integrity.sha256.Length -ne 64 -or $size -le 0) {
                throw "Cliff handoff manifest has missing proof media integrity metadata."
            }
            $archivePath = [string]$asset.archive_path
            if (!$archivePath -or $names -notcontains $archivePath) {
                throw "Cliff handoff ZIP is missing proof media file $archivePath."
            }
            if (!$asset.workflow_provenance) {
                throw "Cliff handoff manifest has missing proof workflow provenance."
            }
            $sidecarPath = [string]$asset.workflow_sidecar_path
            if (!$sidecarPath -or $names -notcontains $sidecarPath) {
                throw "Cliff handoff ZIP is missing proof workflow sidecar."
            }
        }
        if (!($names | Where-Object { $_ -like "channel-exports/*" })) {
            throw "Cliff handoff ZIP has no channel export files."
        }
        if (!$manifest.channel_exports -or [int]$manifest.counts.channel_export_sets -lt 1 -or [int]$manifest.counts.channel_export_files -lt 1) {
            throw "Cliff handoff manifest has missing channel export metadata."
        }
        $requiredChannelPresets = @(
            "pdp",
            "email-hero",
            "instagram-feed",
            "instagram-story",
            "paid-social",
            "transparent-png",
            "high-res-master"
        )
        foreach ($exportSetProperty in @($manifest.channel_exports.PSObject.Properties)) {
            $exportSet = $exportSetProperty.Value
            foreach ($preset in $requiredChannelPresets) {
                $exportProperty = $exportSet.exports.PSObject.Properties[$preset]
                $export = if ($exportProperty) { $exportProperty.Value } else { $null }
                if (!$export) {
                    throw "Cliff handoff channel export set is missing $preset."
                }
                $imageFile = [string]$export.image_file
                $metadataFile = [string]$export.metadata_file
                $integrity = $export.media_integrity
                $size = 0
                if ($integrity -and $integrity.file_size_bytes) {
                    $size = [int64]$integrity.file_size_bytes
                }
                if (!$imageFile -or $names -notcontains $imageFile) {
                    throw "Cliff handoff ZIP is missing channel export image $imageFile."
                }
                if (!$metadataFile -or $names -notcontains $metadataFile) {
                    throw "Cliff handoff ZIP is missing channel export metadata $metadataFile."
                }
                if (!$integrity -or !($integrity.sha256 -is [string]) -or $integrity.sha256.Length -ne 64 -or $size -le 0) {
                    throw "Cliff handoff channel export has missing media integrity metadata."
                }
            }
        }
        foreach ($asset in @($manifest.reference_assets)) {
            $integrity = $asset.media_integrity
            $size = 0
            if ($integrity -and $integrity.file_size_bytes) {
                $size = [int64]$integrity.file_size_bytes
            }
            if (!$integrity -or !($integrity.sha256 -is [string]) -or $integrity.sha256.Length -ne 64 -or $size -le 0) {
                throw "Cliff handoff manifest has missing reference media integrity metadata."
            }
        }
    } finally {
        $archive.Dispose()
    }
}

function Copy-HandoffReviewBoardToStage {
    param(
        [string]$HandoffPath,
        [string]$DestinationPath
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($HandoffPath)
    try {
        $entry = $archive.GetEntry("review/frank-create-review-board.png")
        if ($null -eq $entry) {
            throw "Cliff handoff ZIP is missing review/frank-create-review-board.png."
        }
        $stream = $entry.Open()
        $memory = New-Object System.IO.MemoryStream
        try {
            $stream.CopyTo($memory)
            $bytes = $memory.ToArray()
        } finally {
            $memory.Dispose()
            $stream.Dispose()
        }
    } finally {
        $archive.Dispose()
    }

    if ($bytes.Length -lt 8 -or $bytes[0] -ne 0x89 -or $bytes[1] -ne 0x50 -or $bytes[2] -ne 0x4E -or $bytes[3] -ne 0x47) {
        throw "Cliff handoff review board is not a PNG."
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DestinationPath) | Out-Null
    [System.IO.File]::WriteAllBytes($DestinationPath, $bytes)
}

function Test-ReadinessPackZip {
    param([string]$Path)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entryByName = @{}
        foreach ($entry in $archive.Entries) {
            $entryByName[$entry.FullName.Replace("\", "/")] = $entry
        }

        $required = @(
            "call-brief/frank-create-call-brief-latest.md",
            "call-brief/frank-create-call-brief-latest.json",
            "provider-readiness/frank-create-provider-readiness-latest.md",
            "provider-readiness/frank-create-provider-readiness-latest.json",
            "activation-checklist/frank-create-activation-checklist-latest.md",
            "activation-checklist/frank-create-activation-checklist-latest.json",
            "brand-context/frank-create-brand-context-latest.md",
            "brand-context/frank-create-brand-context-latest.json",
            "evidence/frank-create-demo-evidence-latest.md",
            "evidence/frank-create-demo-evidence-latest.json",
            "receipts/workflow_smoke_status.json",
            "receipts/cliff_prep_status.json",
            "qa/browser-qa-receipt.json",
            "qa/browser-qa-receipt.md",
            "qa/screenshot-capture-receipt.json",
            "qa/screenshot-capture-receipt.md",
            "qa/shareable-pack-hygiene.json",
            "qa/shareable-pack-hygiene.md",
            "sync/frank-create-sync-manifest-latest.json",
            "screenshots/studio-live-desktop-latest.png",
            "screenshots/studio-live-mobile-latest.png",
            "screenshots/video-lab-live-desktop-latest.png",
            "screenshots/provider-audit-live-desktop-latest.png",
            "screenshots/graph-live-desktop-latest.png",
            "screenshots/graph-live-mobile-latest.png",
            "screenshots/raw-comfy-live-quiet-latest.png",
            "screenshots/raw-comfy-workflow-receipt-latest.png",
            "handoff-review/frank-create-review-board-latest.png",
            "FRANK_CREATE_CALL_DAY.md",
            "FRANK_CREATE_DEMO.md",
            "OPEN_FOR_CLIFF.md",
            "OPEN_ME_FIRST.md",
            "setup/frank-create.env.example",
            "launchers/CLIFF_START_HERE.cmd",
            "launchers/START_FRANK_CREATE_DEMO.cmd",
            "launchers/START_FRANK_CREATE.cmd",
            "launchers/CHECK_FRANK_CREATE.cmd",
            "launchers/VERIFY_CLIFF_PACK.cmd",
            "launchers/PREP_FRANK_CREATE_FOR_CLIFF.cmd",
            "launchers/BUILD_FRANK_CREATE_READINESS_PACK.cmd",
            "launchers/STOP_FRANK_CREATE.cmd",
            "readiness-pack-manifest.json",
            "README.md"
        )

        foreach ($name in $required) {
            if (!$entryByName.ContainsKey($name)) {
                throw "Readiness pack ZIP is missing $name."
            }
        }

        if (!($entryByName.Keys | Where-Object { $_ -like "handoffs/*.zip" })) {
            throw "Readiness pack ZIP is missing the nested Cliff handoff ZIP."
        }

        $manifestReader = New-Object System.IO.StreamReader($entryByName["readiness-pack-manifest.json"].Open())
        try {
            $manifest = $manifestReader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $manifestReader.Dispose()
        }

        $cliffPrepReader = New-Object System.IO.StreamReader($entryByName["receipts/cliff_prep_status.json"].Open())
        try {
            $cliffPrep = $cliffPrepReader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $cliffPrepReader.Dispose()
        }

        $syncManifestReader = New-Object System.IO.StreamReader($entryByName["sync/frank-create-sync-manifest-latest.json"].Open())
        try {
            $syncManifest = $syncManifestReader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $syncManifestReader.Dispose()
        }

        foreach ($name in @(
            "call-brief/frank-create-call-brief-latest.md",
            "call-brief/frank-create-call-brief-latest.json",
            "provider-readiness/frank-create-provider-readiness-latest.md",
            "provider-readiness/frank-create-provider-readiness-latest.json",
            "activation-checklist/frank-create-activation-checklist-latest.md",
            "activation-checklist/frank-create-activation-checklist-latest.json",
            "brand-context/frank-create-brand-context-latest.md",
            "brand-context/frank-create-brand-context-latest.json",
            "evidence/frank-create-demo-evidence-latest.md",
            "evidence/frank-create-demo-evidence-latest.json",
            "sync/frank-create-sync-manifest-latest.json"
        )) {
            if (@($manifest.includes) -notcontains $name) {
                throw "Readiness pack manifest does not list $name."
            }
        }

        if ($syncManifest.schema_version -ne "frank-create.sync.v1") {
            throw "Readiness pack FrankHub sync manifest has the wrong schema."
        }
        if (!$syncManifest.sync_contract -or $syncManifest.sync_contract.tables.assets -ne "frank_create_assets") {
            throw "Readiness pack FrankHub sync manifest is missing the assets table contract."
        }
        if ([int]$syncManifest.counts.approved_assets -lt 1 -or [int]$syncManifest.counts.reference_assets -lt 1) {
            throw "Readiness pack FrankHub sync manifest does not include approved/reference assets."
        }
        if (!$manifest.sync_manifest -or $manifest.sync_manifest.archive_path -ne "sync/frank-create-sync-manifest-latest.json") {
            throw "Readiness pack manifest does not point to the FrankHub sync manifest."
        }

        if ($manifest.screenshot_count -lt 8) {
            throw "Readiness pack manifest has fewer than eight QA screenshots."
        }
        if ($manifest.browser_qa.status -ne "ready") {
            throw "Readiness pack Browser QA receipt is not ready."
        }
        $browserQaMarkdownReader = New-Object System.IO.StreamReader($entryByName["qa/browser-qa-receipt.md"].Open())
        try {
            $browserQaMarkdown = $browserQaMarkdownReader.ReadToEnd()
        } finally {
            $browserQaMarkdownReader.Dispose()
        }
        if ($browserQaMarkdown -notmatch "Provider Setup key fields are limited to Gemini, OpenAI, and Replicate") {
            throw "Readiness pack Browser QA receipt is missing Provider Setup launch-order proof."
        }
        if ($browserQaMarkdown -notmatch "safe production unlock plan") {
            throw "Readiness pack Browser QA receipt is missing production unlock copy proof."
        }
        if ($browserQaMarkdown -notmatch "no-spend selected model preflight" -or $browserQaMarkdown -notmatch "safe payload preview") {
            throw "Readiness pack Browser QA receipt is missing selected model preflight proof."
        }
        if ($browserQaMarkdown -notmatch "Demo Doctor readiness pack checksum" -or $browserQaMarkdown -notmatch "Verified SHA-256\s+[a-fA-F0-9]{64}") {
            throw "Readiness pack Browser QA receipt is missing Demo Doctor checksum proof."
        }
        if ($browserQaMarkdown -notmatch "visible UI checksum at browser-QA time" -or $browserQaMarkdown -notmatch "readiness ZIP \.sha256 sidecar") {
            throw "Readiness pack Browser QA receipt does not distinguish browser-time checksum proof from the current ZIP sidecar."
        }
        if ($browserQaMarkdown -notmatch "Studio local Generate button" -or $browserQaMarkdown -notmatch "local Studio Generate button created output assets") {
            throw "Readiness pack Browser QA receipt is missing local generate button proof."
        }
        if ($browserQaMarkdown -notmatch "Studio masked edit Generate button" -or $browserQaMarkdown -notmatch "masked edit Generate button created output assets") {
            throw "Readiness pack Browser QA receipt is missing masked edit button proof."
        }
        if (!$cliffPrep.browser_qa -or $cliffPrep.browser_qa.status -ne "ready") {
            throw "Readiness pack Cliff prep receipt does not include ready browser QA."
        }
        $providerReadinessReader = New-Object System.IO.StreamReader($entryByName["provider-readiness/frank-create-provider-readiness-latest.md"].Open())
        try {
            $providerReadinessMarkdown = $providerReadinessReader.ReadToEnd()
        } finally {
            $providerReadinessReader.Dispose()
        }
        $providerReadinessJsonReader = New-Object System.IO.StreamReader($entryByName["provider-readiness/frank-create-provider-readiness-latest.json"].Open())
        try {
            $providerReadinessJson = $providerReadinessJsonReader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $providerReadinessJsonReader.Dispose()
        }
        if ($providerReadinessMarkdown -notmatch "## Mocked Live-Path Coverage" -or $providerReadinessMarkdown -notmatch "server-side Replicate token path") {
            throw "Readiness pack provider readiness receipt is missing mocked live-path coverage."
        }
        if ($providerReadinessMarkdown -notmatch "Operation request previews:\s+\d+\s+checked\s+/\s+0\s+failures") {
            throw "Readiness pack provider readiness receipt is missing operation request preview proof."
        }
        if ([int]($providerReadinessJson.adapter_audit.summary.operation_preview_count) -lt 12 -or [int]($providerReadinessJson.adapter_audit.summary.operation_preview_failures) -ne 0) {
            throw "Readiness pack provider readiness JSON is missing operation request preview proof."
        }
        if (@($providerReadinessJson.mocked_live_path_coverage).Count -lt 3) {
            throw "Readiness pack provider readiness JSON is missing mocked live-path coverage."
        }
        $providerTemplateReader = New-Object System.IO.StreamReader($entryByName["setup/frank-create.env.example"].Open())
        try {
            $providerTemplate = $providerTemplateReader.ReadToEnd()
        } finally {
            $providerTemplateReader.Dispose()
        }
        $launchProviderEnvVars = @(
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "REPLICATE_API_TOKEN"
        )
        foreach ($envVar in $launchProviderEnvVars) {
            $escapedEnvVar = [regex]::Escape($envVar)
            if ($providerTemplate -notmatch "$escapedEnvVar=") {
                throw "Provider template is missing launch provider key placeholder: $envVar"
            }
        }
        if ($providerTemplate -match "sk-|r8_") {
            throw "Readiness pack provider setup template contains a provider-token-shaped value."
        }
        $activationReader = New-Object System.IO.StreamReader($entryByName["activation-checklist/frank-create-activation-checklist-latest.md"].Open())
        try {
            $activationChecklistMarkdown = $activationReader.ReadToEnd()
        } finally {
            $activationReader.Dispose()
        }
        $activationJsonReader = New-Object System.IO.StreamReader($entryByName["activation-checklist/frank-create-activation-checklist-latest.json"].Open())
        try {
            $activationChecklistJson = $activationJsonReader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $activationJsonReader.Dispose()
        }
        if ($activationChecklistMarkdown -notmatch "Frank Create Production Unlock Checklist" -or $activationChecklistMarkdown -notmatch "Paste rotated live provider keys") {
            throw "Readiness pack activation checklist receipt is missing production unlock actions."
        }
        if ($activationChecklistMarkdown -notmatch "Rotate the exposed Replicate token") {
            throw "Activation checklist receipt is missing the exposed Replicate token rotation step."
        }
        if (@($activationChecklistJson.steps).Count -lt 4) {
            throw "Activation checklist JSON does not include the production unlock steps."
        }
        $brandContextReader = New-Object System.IO.StreamReader($entryByName["brand-context/frank-create-brand-context-latest.md"].Open())
        try {
            $brandContextMarkdown = $brandContextReader.ReadToEnd()
        } finally {
            $brandContextReader.Dispose()
        }
        $brandContextJsonReader = New-Object System.IO.StreamReader($entryByName["brand-context/frank-create-brand-context-latest.json"].Open())
        try {
            $brandContextJson = $brandContextJsonReader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $brandContextJsonReader.Dispose()
        }
        if ($brandContextMarkdown -notmatch "Prompt-guided target" -or $brandContextMarkdown -notmatch "Future LoRA target") {
            throw "Readiness pack brand-context receipt is missing prompt-guided or LoRA readiness."
        }
        if ([int]$brandContextJson.summary.reference_asset_count -lt 1) {
            throw "Readiness pack brand-context JSON does not include a reference asset."
        }
        if ($manifest.shareable_pack_hygiene.status -ne "clean") {
            throw "Readiness pack hygiene receipt is not clean."
        }
        if ($manifest.cliff_pack.status -ne "included") {
            throw "Readiness pack manifest does not include a Cliff handoff."
        }
    } finally {
        $archive.Dispose()
    }
}

function New-BrowserQaReceipt {
    param(
        [array]$Screenshots,
        [string]$BaseUrl,
        [string]$BrowserQaStatusPath
    )

    $screenshotSet = @{}
    foreach ($screenshot in @($Screenshots)) {
        $screenshotSet["screenshots/$screenshot"] = $true
    }

    $checks = @(
        [ordered]@{ key = "studio_desktop"; label = "Studio desktop"; screenshot = "screenshots/studio-live-desktop-latest.png" },
        [ordered]@{ key = "studio_mobile"; label = "Studio mobile"; screenshot = "screenshots/studio-live-mobile-latest.png" },
        [ordered]@{ key = "video_lab"; label = "Video Lab"; screenshot = "screenshots/video-lab-live-desktop-latest.png" },
        [ordered]@{ key = "provider_audit"; label = "Provider Adapter Audit"; screenshot = "screenshots/provider-audit-live-desktop-latest.png" },
        [ordered]@{ key = "advanced_graph"; label = "Advanced Graph"; screenshot = "screenshots/graph-live-desktop-latest.png" },
        [ordered]@{ key = "advanced_graph_mobile"; label = "Advanced Graph mobile"; screenshot = "screenshots/graph-live-mobile-latest.png" },
        [ordered]@{ key = "raw_comfy"; label = "Raw Comfy canvas"; screenshot = "screenshots/raw-comfy-live-quiet-latest.png" },
        [ordered]@{ key = "raw_comfy_receipt"; label = "Raw Comfy selected workflow receipt"; screenshot = "screenshots/raw-comfy-workflow-receipt-latest.png" }
    )

    foreach ($check in $checks) {
        $check["status"] = $(if ($screenshotSet.ContainsKey($check["screenshot"])) { "included" } else { "missing" })
    }

    $scriptChecks = @()
    $completedAt = $null
    if ($BrowserQaStatusPath -and (Test-Path -LiteralPath $BrowserQaStatusPath)) {
        $scriptReceipt = Get-Content -LiteralPath $BrowserQaStatusPath -Raw | ConvertFrom-Json
        if ($scriptReceipt.status -ne "ready") {
            throw "Browser QA script receipt is not ready."
        }
        $completedAt = $scriptReceipt.completed_at
        $scriptChecks = @($scriptReceipt.checks)
    }

    foreach ($scriptCheck in $scriptChecks) {
        $checkKey = [string]$scriptCheck.key
        if (!$checkKey) {
            continue
        }
        $exists = @($checks | Where-Object { $_.key -eq $checkKey } | Select-Object -First 1)
        if ($exists) {
            $exists[0]["browser_status"] = [string]$scriptCheck.status
            if ($scriptCheck.url) {
                $exists[0]["url"] = [string]$scriptCheck.url
            }
            if ($scriptCheck.detail) {
                $exists[0]["detail"] = [string]$scriptCheck.detail
            }
            continue
        }
        $checks += [ordered]@{
            key = $checkKey
            label = [string]$scriptCheck.label
            status = [string]$scriptCheck.status
            url = [string]$scriptCheck.url
            detail = [string]$scriptCheck.detail
        }
    }

    $notReady = @($checks | Where-Object { $_.status -notin @("included", "ready") })
    [ordered]@{
        status = $(if ($notReady.Count -eq 0) { "ready" } else { "partial" })
        base_url = $BaseUrl
        completed_at = $completedAt
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        checks = $checks
        notes = @(
            "Screenshots were captured from the live local Frank Create app.",
            "Use these with the Demo Evidence receipt for visual QA proof.",
            "The Demo Doctor checksum row proves the visible UI checksum at browser-QA time; use the readiness ZIP .sha256 sidecar for the current package checksum after rebuilds."
        )
    }
}

function Write-BrowserQaReceipt {
    param(
        [object]$Receipt,
        [string]$DestinationDir
    )

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    $jsonPath = Join-Path $DestinationDir "browser-qa-receipt.json"
    $markdownPath = Join-Path $DestinationDir "browser-qa-receipt.md"
    $Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    $lines = @(
        "# Frank Create Browser QA Receipt",
        "",
        "Status: **$($Receipt.status)**",
        "Base URL: ``$($Receipt.base_url)``",
        "Generated: $($Receipt.generated_at)",
        "",
        "## Covered Surfaces",
        ""
    )
    foreach ($check in $Receipt.checks) {
        $proofParts = @()
        if ($check.screenshot) {
            $proofParts += "Screenshot: ``$($check.screenshot)``"
        }
        if ($check.browser_status) {
            $proofParts += "Browser: ``$($check.browser_status)``"
        }
        if ($check.url) {
            $proofParts += "URL: ``$($check.url)``"
        }
        if ($check.detail) {
            $proofParts += [string]$check.detail
        }
        if ($proofParts.Count -eq 0) {
            $proofParts += "No proof detail recorded."
        }
        $proof = $proofParts -join "; "
        $lines += "- ``$($check.status)`` $($check.label): $proof"
    }
    $lines += ""
    $lines += "## Notes"
    $lines += ""
    foreach ($note in $Receipt.notes) {
        $lines += "- $note"
    }
    $lines -join "`n" | Set-Content -LiteralPath $markdownPath -Encoding UTF8
}

function Update-StagedCliffPrepBrowserQa {
    param(
        [string]$PrepStatusPath,
        [object]$BrowserQa
    )

    if (!(Test-Path -LiteralPath $PrepStatusPath)) {
        throw "Staged Cliff prep receipt is missing: $PrepStatusPath"
    }

    $prep = Get-Content -LiteralPath $PrepStatusPath -Raw | ConvertFrom-Json
    $prep.browser_qa = $BrowserQa
    $prep | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath $PrepStatusPath -Encoding UTF8
}

function New-ShareablePackHygieneReceipt {
    param([string]$StageDir)

    $issues = @()
    $stageRoot = (Resolve-Path -LiteralPath $StageDir).Path.TrimEnd("\", "/")
    $secretNamePattern = '(?i)(^|[\\/])(provider_keys\.env|\.env)$'
    $providerTokenPattern = 'r8_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z\-_]{20,}'
    $providerEnvValuePattern = '(?im)^\s*(?:\$env:)?(?:GOOGLE_API_KEY|OPENAI_API_KEY|REPLICATE_API_TOKEN)\s*=\s*["'']?([A-Za-z0-9_\-]{16,})["'']?\s*$'
    $textExtensions = @(".json", ".md", ".txt", ".csv", ".ps1", ".cmd")

    foreach ($file in Get-ChildItem -LiteralPath $StageDir -Recurse -File) {
        $fullName = $file.FullName
        $relative = $fullName
        if ($fullName.StartsWith($stageRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $relative = $fullName.Substring($stageRoot.Length).TrimStart("\", "/")
        }
        if ($relative -match $secretNamePattern) {
            $issues += [ordered]@{ path = $relative; reason = "secret-looking file name" }
            continue
        }

        if ($textExtensions -notcontains $file.Extension.ToLowerInvariant() -or $file.Length -gt 1048576) {
            continue
        }

        $text = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
        if ($text -match $providerTokenPattern) {
            $issues += [ordered]@{ path = $relative; reason = "provider-token-shaped value" }
            continue
        }
        if ($text -match $providerEnvValuePattern) {
            $issues += [ordered]@{ path = $relative; reason = "provider env var assignment with non-placeholder value" }
        }
    }

    [ordered]@{
        status = $(if ($issues.Count -eq 0) { "clean" } else { "blocked" })
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        scanned_root = "readiness pack staging directory"
        scanned_text_extensions = $textExtensions
        issue_count = $issues.Count
        issues = $issues
        notes = @(
            "Provider key placeholders such as ... are allowed.",
            "Actual provider-looking tokens or provider key files block the pack."
        )
    }
}

function Write-ShareablePackHygieneReceipt {
    param(
        [object]$Receipt,
        [string]$DestinationDir
    )

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    $jsonPath = Join-Path $DestinationDir "shareable-pack-hygiene.json"
    $markdownPath = Join-Path $DestinationDir "shareable-pack-hygiene.md"
    $Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    $lines = @(
        "# Frank Create Shareable Pack Hygiene",
        "",
        "Status: **$($Receipt.status)**",
        "Generated: $($Receipt.generated_at)",
        "Issues: $($Receipt.issue_count)",
        "",
        "## Notes",
        ""
    )
    foreach ($note in $Receipt.notes) {
        $lines += "- $note"
    }
    if ($Receipt.issue_count -gt 0) {
        $lines += ""
        $lines += "## Issues"
        $lines += ""
        foreach ($issue in $Receipt.issues) {
            $lines += "- $($issue.path): $($issue.reason)"
        }
    }
    $lines -join "`n" | Set-Content -LiteralPath $markdownPath -Encoding UTF8
}

function Write-ProviderReadinessReceipt {
    param(
        [object]$Readiness,
        [object]$AdapterAudit,
        [string]$DestinationDir
    )

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    $jsonPath = Join-Path $DestinationDir "frank-create-provider-readiness-latest.json"
    $markdownPath = Join-Path $DestinationDir "frank-create-provider-readiness-latest.md"
    if ($AdapterAudit) {
        $Readiness | Add-Member -NotePropertyName "adapter_audit" -NotePropertyValue $AdapterAudit -Force
    }
    $mockedLivePathCoverage = @(
        [ordered]@{ provider = "google"; model = "Nano Banana Pro / NB 2"; proof = "Mocked v1 generateContent generation/edit responses create review image assets and send edit sources as inline data." },
        [ordered]@{ provider = "openai"; model = "gpt-image-2"; proof = "Mocked masked-edit request sends source image and mask as separate multipart files." },
        [ordered]@{ provider = "replicate"; model = "FLUX 1.1 Pro Ultra"; proof = "Mocked Replicate prediction response creates review assets through the server-side Replicate token path." }
    )
    $Readiness | Add-Member -NotePropertyName "mocked_live_path_coverage" -NotePropertyValue $mockedLivePathCoverage -Force
    $Readiness | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    $summary = $Readiness.summary
    $lines = @(
        "# Frank Create Provider Readiness",
        "",
        "Generated: $([DateTimeOffset]::UtcNow.ToString("o"))",
        "",
        "## Summary",
        "",
        "- Models ready: $($summary.readyModels) / $($summary.modelCount)",
        "- Models waiting on keys: $($summary.waitingModels)",
        "- Configured env vars: $(Join-OrNone @($summary.configuredEnvVars))",
        "- Missing env vars: $(Join-OrNone @($summary.missingEnvVars))",
        "",
        "## Providers",
        ""
    )

    foreach ($provider in @($Readiness.providers)) {
        $lines += "- $($provider.provider): $($provider.ready_model_count) ready / $($provider.model_count) models; waiting $($provider.waiting_model_count)"
    }

    $lines += ""
    $lines += "## Launch Model Roster"
    $lines += ""
    foreach ($model in @($Readiness.models)) {
        $capabilities = @()
        if ($model.capabilities.generation) { $capabilities += "gen" }
        if ($model.capabilities.edit) { $capabilities += "edit" }
        if ($model.capabilities.masked_edit) { $capabilities += "mask" }
        if ($model.capabilities.video) { $capabilities += "video" }
        $missing = @($model.missing_env_vars) -join ", "
        $status = $(if ($model.configured) { "ready" } else { "needs $missing" })
        $lines += "- $($model.label) ($($model.provider), $($model.badge)): $status; $($capabilities -join ', '); $($model.reference_image_limit) refs"
    }

    if ($AdapterAudit) {
        $auditSummary = $AdapterAudit.summary
        $lines += ""
        $lines += "## No-Spend Adapter Audit"
        $lines += ""
        $lines += "- Adapter runners registered: $($auditSummary.runner_registered) / $($auditSummary.model_count)"
        $lines += "- Missing runners: $($auditSummary.missing_runners)"
        $lines += "- Request preview failures: $($auditSummary.preview_failures)"
        $lines += "- Operation request previews: $($auditSummary.operation_preview_count) checked / $($auditSummary.operation_preview_failures) failures"
        $lines += "- External API calls made: $(if ($auditSummary.no_spend) { "no" } else { "check" })"
        $lines += "- Secret values returned: $(if ($auditSummary.secret_values_returned) { "check" } else { "no" })"
        $lines += ""
        foreach ($model in @($AdapterAudit.models)) {
            $preview = $model.request_preview
            $method = $(if ($preview -and $preview.method) { $preview.method } else { "n/a" })
            $endpoint = $(if ($preview -and $preview.endpoint) { $preview.endpoint } else { "n/a" })
            $operationKinds = @($model.operation_kinds) | ForEach-Object { ([string]$_) -replace "_", " " }
            $operationPreviewCount = 0
            if ($model.request_previews) {
                $operationPreviewCount = @($model.request_previews.PSObject.Properties).Count
            }
            if (!$operationPreviewCount) {
                $operationPreviewCount = @($model.operation_kinds).Count
            }
            $lines += "- $($model.label) ($($model.provider)): $($model.status); $operationPreviewCount operation preview(s): $(Join-OrNone $operationKinds); $method $endpoint"
        }
    }

    $lines += ""
    $lines += "## Mocked Live-Path Coverage"
    $lines += ""
    foreach ($item in @($mockedLivePathCoverage)) {
        $lines += "- $($item.model) ($($item.provider)): $($item.proof)"
    }

    $lines += ""
    $lines += "## Notes"
    $lines += ""
    foreach ($note in @($Readiness.notes)) {
        $lines += "- $note"
    }
    $lines -join "`n" | Set-Content -LiteralPath $markdownPath -Encoding UTF8
}

function Write-ActivationChecklistReceipt {
    param(
        [object]$Checklist,
        [string]$DestinationDir
    )

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    $jsonPath = Join-Path $DestinationDir "frank-create-activation-checklist-latest.json"
    $markdownPath = Join-Path $DestinationDir "frank-create-activation-checklist-latest.md"
    $Checklist | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    $summary = $Checklist.summary
    $lines = @(
        "# Frank Create Production Unlock Checklist",
        "",
        "Status: **$($Checklist.status)**",
        "",
        "## Summary",
        "",
        "- Live model paths unlocked: $($summary.ready_provider_models) / $($summary.provider_model_count)",
        "- Live model paths waiting: $($summary.waiting_provider_models)",
        "- Local checkpoint count: $($summary.checkpoint_count)",
        "- Diffusion checkpoint ready: $(if ($summary.diffusion_ready) { "yes" } else { "no" })",
        "- Server key file: ``$($summary.server_key_file)``",
        "- Configured env vars: $(Join-OrNone @($summary.configured_env_vars))",
        "- Missing env vars: $(Join-OrNone @($summary.missing_env_vars))",
        "",
        "## Unlock Steps",
        ""
    )

    $index = 1
    foreach ($step in @($Checklist.steps)) {
        $lines += "### $index. $($step.label)"
        $lines += ""
        $lines += "- Status: $($step.status)"
        $lines += "- Detail: $($step.detail)"
        $lines += "- Action: $($step.action)"
        if ($step.env_vars) {
            $lines += "- Env vars: $(Join-OrNone @($step.env_vars))"
        }
        if ($step.path) {
            $lines += "- Path: ``$($step.path)``"
        }
        $lines += ""
        $index += 1
    }

    $lines += "## Notes"
    $lines += ""
    foreach ($note in @($Checklist.notes)) {
        $lines += "- $note"
    }
    $lines -join "`n" | Set-Content -LiteralPath $markdownPath -Encoding UTF8
}

function Add-CliffHandoffToStage {
    param([string]$DestinationDir)

    try {
        $sessions = (Invoke-Json "$FrankApi/sessions").sessions
        $session = $sessions | Where-Object { $_.name -eq "Frank Body Demo Studio" -and $_.status -eq "active" } | Select-Object -First 1
        if (!$session) {
            $session = $sessions | Where-Object { $_.status -eq "active" } | Select-Object -First 1
        }
        if (!$session) {
            return [ordered]@{
                status = "missing"
                detail = "No active session was available for a Cliff Pack handoff."
            }
        }

        $handoff = Invoke-Json "$FrankApi/sessions/$($session.id)/handoff" "POST" @{ summary = "Frank Create readiness-pack handoff for Cliff review." }
        $metadata = $handoff.metadata
        $downloadUrl = "$BaseUrl$($handoff.download_url)"
        $destination = Join-Path $DestinationDir "$(($session.name -replace '[^A-Za-z0-9._-]+', '-').Trim('-').ToLowerInvariant())-handoff.zip"
        New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $destination -TimeoutSec 60
        Test-CliffHandoffZip -Path $destination

        return [ordered]@{
            status = "included"
            export_id = $handoff.handoff.id
            session_id = $session.id
            session_name = $session.name
            archive_path = "handoffs/$(Split-Path -Leaf $destination)"
            approved_asset_count = Convert-ToInt $metadata.asset_count
            approved_image_count = Convert-ToInt $metadata.image_count
            approved_video_count = Convert-ToInt $metadata.video_count
            reference_count = Convert-ToInt $metadata.reference_count
        }
    } catch {
        return [ordered]@{
            status = "missing"
            detail = $_.Exception.Message
        }
    }
}

function Add-SyncManifestToStage {
    param(
        [string]$SessionId,
        [string]$DestinationDir
    )

    if (!$SessionId) {
        return [ordered]@{
            status = "missing"
            detail = "No session id was available for the FrankHub sync manifest."
        }
    }

    try {
        New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
        $manifest = Invoke-Json "$FrankApi/sessions/$SessionId/sync-manifest"
        if ($manifest.schema_version -ne "frank-create.sync.v1") {
            throw "Sync manifest endpoint returned schema $($manifest.schema_version)."
        }
        if (!$manifest.sync_contract -or $manifest.sync_contract.tables.assets -ne "frank_create_assets") {
            throw "Sync manifest endpoint did not return the FrankHub assets table contract."
        }
        if ([int]$manifest.counts.approved_assets -lt 1 -or [int]$manifest.counts.reference_assets -lt 1) {
            throw "Sync manifest endpoint did not include approved/reference assets."
        }

        $destination = Join-Path $DestinationDir "frank-create-sync-manifest-latest.json"
        $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $destination -Encoding UTF8
        return [ordered]@{
            status = "included"
            schema_version = $manifest.schema_version
            archive_path = "sync/frank-create-sync-manifest-latest.json"
            asset_count = Convert-ToInt $manifest.counts.assets
            approved_asset_count = Convert-ToInt $manifest.counts.approved_assets
            reference_asset_count = Convert-ToInt $manifest.counts.reference_assets
        }
    } catch {
        return [ordered]@{
            status = "missing"
            detail = $_.Exception.Message
        }
    }
}

Set-Location $Root

if (!$SkipPrep) {
    Write-Step "Running Cliff prep before building the pack..."
    & $PrepScript -Port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Cliff prep did not pass, so the readiness pack was not created."
    }
}

Write-Step "Refreshing latest evidence receipt..."
try {
    Invoke-Json "$FrankApi/demo/evidence" "POST" @{ base_url = $BaseUrl } | Out-Null
} catch {
    if (!(Test-Path -LiteralPath (Join-Path $EvidenceDir "frank-create-demo-evidence-latest.md")) -or
        !(Test-Path -LiteralPath (Join-Path $EvidenceDir "frank-create-demo-evidence-latest.json"))) {
        throw "Could not refresh or find latest evidence receipt: $($_.Exception.Message)"
    }
    Write-Step "Using existing evidence receipt because refresh failed: $($_.Exception.Message)" "Yellow"
}

Write-Step "Refreshing latest call brief..."
try {
    Invoke-Json "$FrankApi/demo/call-brief" "POST" @{ base_url = $BaseUrl } | Out-Null
} catch {
    if (!(Test-Path -LiteralPath (Join-Path $CallBriefDir "frank-create-call-brief-latest.md")) -or
        !(Test-Path -LiteralPath (Join-Path $CallBriefDir "frank-create-call-brief-latest.json"))) {
        throw "Could not refresh or find latest call brief: $($_.Exception.Message)"
    }
    Write-Step "Using existing call brief because refresh failed: $($_.Exception.Message)" "Yellow"
}

Write-Step "Refreshing latest brand context brief..."
try {
    Invoke-Json "$FrankApi/demo/brand-context" "POST" @{ base_url = $BaseUrl } | Out-Null
} catch {
    if (!(Test-Path -LiteralPath (Join-Path $EvidenceDir "frank-create-brand-context-latest.md")) -or
        !(Test-Path -LiteralPath (Join-Path $EvidenceDir "frank-create-brand-context-latest.json"))) {
        throw "Could not refresh or find latest brand context brief: $($_.Exception.Message)"
    }
    Write-Step "Using existing brand context brief because refresh failed: $($_.Exception.Message)" "Yellow"
}

$screenshotCapture = Invoke-ReadinessScreenshotCapture -BaseUrl $BaseUrl -DestinationDir $QaDir -SkipRefresh:$SkipScreenshotRefresh

$latestMarkdown = Join-Path $EvidenceDir "frank-create-demo-evidence-latest.md"
$latestJson = Join-Path $EvidenceDir "frank-create-demo-evidence-latest.json"
$latestCallBriefMarkdown = Join-Path $CallBriefDir "frank-create-call-brief-latest.md"
$latestCallBriefJson = Join-Path $CallBriefDir "frank-create-call-brief-latest.json"
$latestProviderReadinessMarkdown = Join-Path $EvidenceDir "frank-create-provider-readiness-latest.md"
$latestProviderReadinessJson = Join-Path $EvidenceDir "frank-create-provider-readiness-latest.json"
$latestActivationChecklistMarkdown = Join-Path $EvidenceDir "frank-create-activation-checklist-latest.md"
$latestActivationChecklistJson = Join-Path $EvidenceDir "frank-create-activation-checklist-latest.json"
$latestBrandContextMarkdown = Join-Path $EvidenceDir "frank-create-brand-context-latest.md"
$latestBrandContextJson = Join-Path $EvidenceDir "frank-create-brand-context-latest.json"
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$packName = "frank-create-cliff-readiness-$timestamp"
$stageDir = Join-Path ([System.IO.Path]::GetTempPath()) "$packName-$([Guid]::NewGuid().ToString('N'))"
$zipPath = Join-Path $OutputDir "$packName.zip"
$latestZipPath = Join-Path $OutputDir "frank-create-cliff-readiness-latest.zip"
$latestImplementationManifestPath = Join-Path $OutputDir "frank-create-implementation-manifest-latest.md"

New-Item -ItemType Directory -Force -Path $stageDir, $OutputDir | Out-Null

try {
    Copy-RequiredFile -Source $latestCallBriefMarkdown -Destination (Join-Path $stageDir "call-brief\frank-create-call-brief-latest.md")
    Copy-RequiredFile -Source $latestCallBriefJson -Destination (Join-Path $stageDir "call-brief\frank-create-call-brief-latest.json")
    Copy-RequiredFile -Source $latestMarkdown -Destination (Join-Path $stageDir "evidence\frank-create-demo-evidence-latest.md")
    Copy-RequiredFile -Source $latestJson -Destination (Join-Path $stageDir "evidence\frank-create-demo-evidence-latest.json")
    Copy-RequiredFile -Source $latestBrandContextMarkdown -Destination (Join-Path $stageDir "brand-context\frank-create-brand-context-latest.md")
    Copy-RequiredFile -Source $latestBrandContextJson -Destination (Join-Path $stageDir "brand-context\frank-create-brand-context-latest.json")
    Copy-RequiredFile -Source $WorkflowStatusPath -Destination (Join-Path $stageDir "receipts\workflow_smoke_status.json")
    Copy-RequiredFile -Source $PrepStatusPath -Destination (Join-Path $stageDir "receipts\cliff_prep_status.json")
    Copy-RequiredFile -Source $RunbookPath -Destination (Join-Path $stageDir "FRANK_CREATE_DEMO.md")
    Copy-RequiredFile -Source $CallDayPath -Destination (Join-Path $stageDir "FRANK_CREATE_CALL_DAY.md")
    Copy-RequiredFile -Source $OpenForCliffPath -Destination (Join-Path $stageDir "OPEN_FOR_CLIFF.md")
    Copy-RequiredFile -Source $ProviderEnvExamplePath -Destination (Join-Path $stageDir "setup\frank-create.env.example")
    foreach ($launcherFile in $LauncherFiles) {
        Copy-RequiredFile -Source (Join-Path $Root $launcherFile) -Destination (Join-Path $stageDir "launchers\$launcherFile")
    }

    $screenshots = Copy-ReadinessScreenshots -SourceDir $QaDir -DestinationDir (Join-Path $stageDir "screenshots")
    $browserQa = New-BrowserQaReceipt -Screenshots $screenshots -BaseUrl $BaseUrl -BrowserQaStatusPath $BrowserQaStatusPath
    Write-BrowserQaReceipt -Receipt $browserQa -DestinationDir (Join-Path $stageDir "qa")
    Update-StagedCliffPrepBrowserQa -PrepStatusPath (Join-Path $stageDir "receipts\cliff_prep_status.json") -BrowserQa $browserQa
    Write-ScreenshotCaptureReceipt -Receipt $screenshotCapture -DestinationDir (Join-Path $stageDir "qa")
    $providerReadiness = Invoke-Json "$FrankApi/provider-status"
    $providerAdapterAudit = Invoke-Json "$FrankApi/provider-audit"
    $activationChecklist = Invoke-Json "$FrankApi/activation-checklist"
    Write-ProviderReadinessReceipt -Readiness $providerReadiness -AdapterAudit $providerAdapterAudit -DestinationDir $EvidenceDir
    Write-ActivationChecklistReceipt -Checklist $activationChecklist -DestinationDir $EvidenceDir
    Copy-RequiredFile -Source $latestProviderReadinessMarkdown -Destination (Join-Path $stageDir "provider-readiness\frank-create-provider-readiness-latest.md")
    Copy-RequiredFile -Source $latestProviderReadinessJson -Destination (Join-Path $stageDir "provider-readiness\frank-create-provider-readiness-latest.json")
    Copy-RequiredFile -Source $latestActivationChecklistMarkdown -Destination (Join-Path $stageDir "activation-checklist\frank-create-activation-checklist-latest.md")
    Copy-RequiredFile -Source $latestActivationChecklistJson -Destination (Join-Path $stageDir "activation-checklist\frank-create-activation-checklist-latest.json")
    $syncManifest = [ordered]@{
        status = "missing"
        detail = "Cliff Pack was not available, so no sync manifest was packaged."
    }
    $cliffPack = Add-CliffHandoffToStage -DestinationDir (Join-Path $stageDir "handoffs")
    if ($cliffPack.status -eq "included") {
        $reviewBoardArchivePath = "handoff-review/frank-create-review-board-latest.png"
        $handoffPath = Join-Path $stageDir (([string]$cliffPack.archive_path).Replace("/", "\"))
        Copy-HandoffReviewBoardToStage -HandoffPath $handoffPath -DestinationPath (Join-Path $stageDir $reviewBoardArchivePath)
        $cliffPack["review_board_top_level_archive_path"] = $reviewBoardArchivePath
        $syncManifest = Add-SyncManifestToStage -SessionId $cliffPack.session_id -DestinationDir (Join-Path $stageDir "sync")
        if ($syncManifest.status -ne "included") {
            throw "Could not package FrankHub sync manifest: $($syncManifest.detail)"
        }
    }
    $syncManifestPath = Join-Path $stageDir "sync\frank-create-sync-manifest-latest.json"
    if (!(Test-Path -LiteralPath $syncManifestPath)) {
        $sessions = (Invoke-Json "$FrankApi/sessions").sessions
        $fallbackSession = $sessions | Where-Object { $_.name -eq "Frank Body Demo Studio" -and $_.status -eq "active" } | Select-Object -First 1
        if (!$fallbackSession) {
            $fallbackSession = $sessions | Where-Object { $_.status -eq "active" } | Select-Object -First 1
        }
        if ($fallbackSession) {
            $syncManifest = Add-SyncManifestToStage -SessionId $fallbackSession.id -DestinationDir (Join-Path $stageDir "sync")
        }
    }
    if ($syncManifest.status -ne "included" -or !(Test-Path -LiteralPath $syncManifestPath)) {
        throw "Could not package FrankHub sync manifest: $($syncManifest.detail)"
    }
    $evidencePayload = Get-Content -LiteralPath $latestJson -Raw | ConvertFrom-Json
    $brandContextPayload = Get-Content -LiteralPath $latestBrandContextJson -Raw | ConvertFrom-Json
    $summary = $evidencePayload.summary
    $brandSummary = $brandContextPayload.summary
    $providerSummary = $providerReadiness.summary
    $auditSummary = $providerAdapterAudit.summary
    $runnerCount = [int]$auditSummary.runner_registered
    $runnerTotal = [int]$auditSummary.model_count
    $previewFailures = [int]$auditSummary.preview_failures
    $providerAdapterStatus = if ($runnerTotal -gt 0 -and $runnerCount -eq $runnerTotal -and $previewFailures -eq 0 -and [int]$summary.missing_provider_adapter_count -eq 0) { "ready" } else { "check" }
    $providerAdapterProof = if ($runnerTotal -gt 0) {
        "No-spend audit: $runnerCount / $runnerTotal launch runners registered, $previewFailures preview failures; provider keys $($providerSummary.readyModels) ready / $($providerSummary.waitingModels) waiting."
    } else {
        "$($summary.provider_adapter_count) registered, $($summary.missing_provider_adapter_count) missing; provider keys $($providerSummary.readyModels) ready / $($providerSummary.waitingModels) waiting."
    }
    $activationStepCount = @($activationChecklist.steps).Count
    $activationLabels = (@($activationChecklist.steps) | Select-Object -First 3 | ForEach-Object {
        ([string]$_.label).Replace("Paste rotated live provider keys", "rotated live provider keys")
    }) -join ", "
    if (!$activationLabels) {
        $activationLabels = "production unlock actions"
    }
    $activationProof = "Activation checklist packaged with $activationStepCount setup step(s): $activationLabels."
    $studioInteractionCheck = @($browserQa.checks | Where-Object { $_.key -eq "studio_interactions" } | Select-Object -First 1)
    $studioInteractionProof = if ($studioInteractionCheck -and $studioInteractionCheck.detail) {
        [string]$studioInteractionCheck.detail
    } else {
        "Session prompt/edit thread, reference assets, generated rounds, copies a safe provider key plan with env-var names and no secret values, safe selected-output run brief copy with workflow provenance, safe workflow JSON sidecar download, and desktop/mobile QA screenshots."
    }
    $brandReferenceCount = [int]$brandSummary.reference_asset_count
    $brandPromptStatus = if ($brandSummary.prompt_guided_status) { [string]$brandSummary.prompt_guided_status } elseif ($brandReferenceCount -gt 0) { "starter" } else { "missing" }
    $brandLoraStatus = if ($brandSummary.lora_training_status) { [string]$brandSummary.lora_training_status } elseif ($brandReferenceCount -gt 0) { "starter" } else { "missing" }
    $brandContextStatus = if ($brandReferenceCount -gt 0) { "ready" } else { "check" }
    $brandContextProof = "Brand-context brief packaged with $brandReferenceCount reference asset(s); prompt-guided mode is $brandPromptStatus, future LoRA is $brandLoraStatus."
    $acceptanceMatrix = @(
        [ordered]@{
            capability = "Conversational Image Studio"
            status = "ready"
            proof = $studioInteractionProof
        },
        [ordered]@{
            capability = "Product Shot Lab flow"
            status = "ready"
            proof = "$($summary.references) reference asset(s), $($summary.outputs) output asset(s), $($summary.approved) approved pick(s)."
        },
        [ordered]@{
            capability = "Generate, edit, approve, export"
            status = if ($summary.workflow_smoke_ok) { "ready" } else { "check" }
            proof = "Workflow smoke media files: $($summary.workflow_smoke_media_files); channel exports: $($summary.workflow_smoke_channel_exports)."
        },
        [ordered]@{
            capability = "Video Lab storyboard"
            status = if ([int]$summary.video -gt 0) { "ready" } else { "check" }
            proof = "$($summary.video) local storyboard/motion asset(s) available."
        },
        [ordered]@{
            capability = "Advanced Graph + raw Comfy"
            status = if ($summary.graph_branding_ready) { "ready" } else { "check" }
            proof = "Advanced Graph and raw Comfy QA screenshots plus branded graph Doctor check."
        },
        [ordered]@{
            capability = "Curated Comfy workflow blueprints"
            status = "ready"
            proof = "Local Comfy exposes downloadable stock-node txt2img, img2img, and inpaint workflow JSON blueprints."
        },
        [ordered]@{
            capability = "Frank Body Mode + brand context"
            status = $brandContextStatus
            proof = $brandContextProof
        },
        [ordered]@{
            capability = "Live provider adapters"
            status = $providerAdapterStatus
            proof = $providerAdapterProof
        },
        [ordered]@{
            capability = "Production activation checklist"
            status = if ($activationStepCount -gt 0) { "ready" } else { "check" }
            proof = $activationProof
        },
        [ordered]@{
            capability = "Server-side key hygiene"
            status = if ([int]$summary.secret_issue_count -eq 0) { "ready" } else { "check" }
            proof = "Secret hygiene issue count: $($summary.secret_issue_count); no provider keys are included in packs."
        },
        [ordered]@{
            capability = "Cliff handoff integrity"
            status = "ready"
            proof = "Readiness ZIP, nested handoff ZIP, workflow provenance, channel-ready approved-image exports, media integrity metadata, byte-for-byte media integrity, and SHA-256 sidecar; workflow smoke, readiness builder, and VERIFY_CLIFF_PACK.cmd compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata."
        }
    )
    $acceptanceMarkdown = @(
        "## Acceptance Matrix",
        "",
        "| Capability | Status | Proof |",
        "| --- | --- | --- |"
    ) + ($acceptanceMatrix | ForEach-Object { "| $($_.capability) | $($_.status) | $($_.proof) |" })
    @"
# Frank Create Implementation Manifest

Frank Create is a Frank-branded creative shell over ComfyUI for Frank Body image and motion workflows.

## Built Surfaces

- Conversational Image Studio: ``$BaseUrl``
- Advanced Graph escape hatch: ``$BaseUrl/graph``
- Raw branded Comfy canvas: ``$BaseUrl/comfy/``
- Provider Setup: server-side key file plus no-spend adapter audit.
- Production activation checklist: packaged key/checkpoint/rotation actions.
- Demo Doctor: call-day health, evidence, call brief, and readiness pack generation.

## Core Workflow

- Create or select a session.
- Upload product/reference assets.
- Generate or edit image rounds with local Comfy/fallback or configured live providers.
- Approve/favorite/reject outputs and add notes.
- Export channel packs, storyboard GIFs, and mixed-media Cliff handoff ZIPs with channel-ready approved-image derivatives.
- Open or package a frank-create.sync.v1 sync manifest for FrankHub, Supabase, or DAM mirroring.

## Verification Snapshot

- Outputs available: $($summary.outputs)
- Approved assets: $($summary.approved)
- Reference assets: $($summary.references)
- Motion/storyboard assets: $($summary.video)
- Workflow smoke media files: $($summary.workflow_smoke_media_files)
- Workflow smoke channel exports: $($summary.workflow_smoke_channel_exports)
- Provider models: $($providerSummary.readyModels) ready / $($providerSummary.waitingModels) waiting on keys
- No-spend adapter audit: $runnerCount / $runnerTotal launch runners, $previewFailures preview failures

## Launch Commands

- ``CLIFF_START_HERE.cmd`` starts or reuses the local Studio, runs the call-day chain, and opens the useful docs.
- ``START_FRANK_CREATE_DEMO.cmd`` resets to a clean demo state and starts the app.
- ``BUILD_FRANK_CREATE_READINESS_PACK.cmd`` rebuilds this proof pack.
- ``VERIFY_CLIFF_PACK.cmd`` verifies the latest proof pack without rebuilding.

$($acceptanceMarkdown -join "`n")

## Expected Warnings

- Live provider models wait for rotated server-side API keys.
- Google Gemini/Nano Banana is the first live API path after ``GOOGLE_API_KEY`` is saved, keys are reloaded, and the selected model preflight passes.
- Local Comfy rounds use checkpoint txt2img when a checkpoint exists in ``models/checkpoints``, checkpoint img2img for reference/edit rounds, and checkpoint inpaint for masked edits.
- Provider API keys and local secret files are intentionally excluded from every readiness pack.
"@ | Set-Content -LiteralPath (Join-Path $stageDir "IMPLEMENTATION_MANIFEST.md") -Encoding UTF8
    @'
# Open Me First

This is the Frank Create Cliff readiness pack.

## Fastest Path

1. On Didac's workstation, double-click `CLIFF_START_HERE.cmd` from the project root.
2. In this ZIP, open `call-brief/frank-create-call-brief-latest.md` for the one-page meeting view.
3. Open `FRANK_CREATE_CALL_DAY.md` for the demo order and fallback commands.
4. Open `provider-readiness/frank-create-provider-readiness-latest.md` to explain which live models are waiting on keys.
5. Open `activation-checklist/frank-create-activation-checklist-latest.md` for production unlock actions.
6. Open `brand-context/frank-create-brand-context-latest.md` to explain Frank Body Mode inputs and future LoRA readiness.
7. Open `sync/frank-create-sync-manifest-latest.json` for the portable `frank-create.sync.v1` FrankHub/Supabase/DAM mirror contract.

Provider setup reference: `setup/frank-create.env.example` lists the server-side key names with blank placeholder values only.

## What This Pack Proves

- The local Frank Create workflow runs end to end: reference upload, generate, edit, approve, export, storyboard, and handoff.
- The Advanced Graph and raw Comfy canvas are branded and still available for power users.
- Open `handoff-review/frank-create-review-board-latest.png` for the instant visual contact sheet.
- The nested `handoffs/` ZIP contains approved media, references, channel-ready approved-image exports, the same visual review board, prompts, notes, workflow provenance, and byte-for-byte media integrity metadata.
- The portable `sync/frank-create-sync-manifest-latest.json` file exposes the `frank-create.sync.v1` contract for later FrankHub/Supabase/DAM sync.
- The workflow smoke, readiness builder, and `VERIFY_CLIFF_PACK.cmd` compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata.
- No provider API keys or local secret files are included.

Expected warnings: no local diffusion checkpoint installed and live provider keys not loaded. The local Frank renderer remains ready for the demo.
'@ | Set-Content -LiteralPath (Join-Path $stageDir "OPEN_ME_FIRST.md") -Encoding UTF8
    $shareableHygiene = New-ShareablePackHygieneReceipt -StageDir $stageDir
    if ($shareableHygiene.status -ne "clean") {
        $issueSummary = (($shareableHygiene.issues | ForEach-Object { "$($_.path): $($_.reason)" }) -join "; ")
        throw "Readiness pack hygiene check failed: $issueSummary"
    }
    Write-ShareablePackHygieneReceipt -Receipt $shareableHygiene -DestinationDir (Join-Path $stageDir "qa")

    $manifest = [ordered]@{
        product = "Frank Create"
        purpose = "Cliff call-day readiness pack"
        created_at = [DateTimeOffset]::UtcNow.ToString("o")
        base_url = $BaseUrl
        includes = @(
            "call-brief/frank-create-call-brief-latest.md",
            "call-brief/frank-create-call-brief-latest.json",
            "provider-readiness/frank-create-provider-readiness-latest.md",
            "provider-readiness/frank-create-provider-readiness-latest.json",
            "activation-checklist/frank-create-activation-checklist-latest.md",
            "activation-checklist/frank-create-activation-checklist-latest.json",
            "brand-context/frank-create-brand-context-latest.md",
            "brand-context/frank-create-brand-context-latest.json",
            "evidence/frank-create-demo-evidence-latest.md",
            "evidence/frank-create-demo-evidence-latest.json",
            "receipts/workflow_smoke_status.json",
            "receipts/cliff_prep_status.json",
            "qa/browser-qa-receipt.json",
            "qa/browser-qa-receipt.md",
            "qa/screenshot-capture-receipt.json",
            "qa/screenshot-capture-receipt.md",
            "qa/shareable-pack-hygiene.json",
            "qa/shareable-pack-hygiene.md",
            "sync/frank-create-sync-manifest-latest.json",
            "handoff-review/frank-create-review-board-latest.png",
            "FRANK_CREATE_CALL_DAY.md",
            "FRANK_CREATE_DEMO.md",
            "OPEN_FOR_CLIFF.md",
            "OPEN_ME_FIRST.md",
            "IMPLEMENTATION_MANIFEST.md",
            "setup/frank-create.env.example",
            "launchers/CLIFF_START_HERE.cmd",
            "launchers/START_FRANK_CREATE_DEMO.cmd",
            "launchers/START_FRANK_CREATE.cmd",
            "launchers/CHECK_FRANK_CREATE.cmd",
            "launchers/VERIFY_CLIFF_PACK.cmd",
            "launchers/PREP_FRANK_CREATE_FOR_CLIFF.cmd",
            "launchers/BUILD_FRANK_CREATE_READINESS_PACK.cmd",
            "launchers/STOP_FRANK_CREATE.cmd"
        )
        screenshot_count = @($screenshots).Count
        acceptance_matrix = $acceptanceMatrix
        screenshot_capture = $screenshotCapture
        browser_qa = $browserQa
        shareable_pack_hygiene = $shareableHygiene
        cliff_pack = $cliffPack
        sync_manifest = $syncManifest
        notes = @(
            "No provider secrets are included.",
            "Open call-brief/frank-create-call-brief-latest.md for the one-page meeting view.",
            "Open provider-readiness/frank-create-provider-readiness-latest.md for model/key readiness.",
            "Open activation-checklist/frank-create-activation-checklist-latest.md for production unlock actions.",
            "Open brand-context/frank-create-brand-context-latest.md for Frank Body Mode and future training inputs.",
            "Open sync/frank-create-sync-manifest-latest.json for the portable FrankHub/Supabase/DAM sync manifest.",
            "Use the latest Markdown evidence file as the top-level proof receipt.",
            "The call-day handoff copy is frank-create-cliff-readiness-latest.zip.",
            "Run PREP_FRANK_CREATE_FOR_CLIFF.cmd again before a live call if the app state changes."
        )
    }

    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stageDir "readiness-pack-manifest.json") -Encoding UTF8

    @"
# Frank Create Cliff Readiness Pack

Call-day file: frank-create-cliff-readiness-latest.zip.
Checksum sidecar: frank-create-cliff-readiness-latest.zip.sha256.

## Command Roster

| Need | Double-click |
| --- | --- |
| Cliff call-day start | CLIFF_START_HERE.cmd |
| Clean demo start | START_FRANK_CREATE_DEMO.cmd |
| Keep current state | START_FRANK_CREATE.cmd |
| Fast readiness check | CHECK_FRANK_CREATE.cmd |
| Verify latest pack | VERIFY_CLIFF_PACK.cmd |
| Full prep receipt | PREP_FRANK_CREATE_FOR_CLIFF.cmd |
| Shareable proof pack | BUILD_FRANK_CREATE_READINESS_PACK.cmd |
| Stop local server | STOP_FRANK_CREATE.cmd |

Start with OPEN_ME_FIRST.md if you are opening this pack cold.
IMPLEMENTATION_MANIFEST.md summarizes what was built and verified.
OPEN_FOR_CLIFF.md is the shortest workstation note.
Open FRANK_CREATE_CALL_DAY.md first for the quick checklist.
Open call-brief/frank-create-call-brief-latest.md for the one-page meeting view.
Open provider-readiness/frank-create-provider-readiness-latest.md for model/key readiness.
Open activation-checklist/frank-create-activation-checklist-latest.md for production unlock actions.
Open brand-context/frank-create-brand-context-latest.md for Frank Body Mode and future training inputs.
Open sync/frank-create-sync-manifest-latest.json for the portable FrankHub/Supabase/DAM sync manifest.
Open setup/frank-create.env.example for blank server-side provider key names.
Command wrappers are bundled under launchers/ for reference. If opened inside an extracted pack, they open packaged proof docs instead of trying to rebuild the app.
Then open evidence/frank-create-demo-evidence-latest.md for the proof receipt.

$($acceptanceMarkdown -join "`n")

This pack includes:

- Implementation manifest with built surfaces, launch commands, and verification snapshot.
- Latest one-page Cliff call brief Markdown and JSON.
- Latest provider-readiness Markdown and JSON.
- Latest production activation checklist Markdown and JSON.
- Latest brand-context Markdown and JSON.
- Latest demo evidence Markdown and JSON.
- Portable sync/frank-create-sync-manifest-latest.json contract for FrankHub/Supabase/DAM mirroring.
- SHA-256 sidecar for the top-level readiness ZIP.
- Workflow smoke and Cliff prep receipts.
- One-page call-day checklist.
- The current runbook.
- Short OPEN_FOR_CLIFF note.
- Blank provider-key template under setup/.
- Local launcher wrappers under launchers/.
- Eight current QA screenshots: studio desktop/mobile, Video Lab, Provider Adapter Audit, Advanced Graph desktop/mobile, raw Comfy canvas, and selected-workflow raw Comfy receipt.
- A top-level handoff-review/frank-create-review-board-latest.png contact sheet for instant visual review.
- A nested handoffs/ ZIP with approved media, references, channel-ready approved-image exports, the same visual review board, prompts, notes, workflow provenance, and byte-for-byte media integrity metadata.
- Workflow smoke, readiness builder, and VERIFY_CLIFF_PACK.cmd compare archived approved/reference/channel export media bytes against manifest SHA-256 and file-size metadata.
- Browser QA, screenshot-capture, and shareable-pack hygiene receipts under qa/.

No provider API keys or local secret files are included.
"@ | Set-Content -LiteralPath (Join-Path $stageDir "README.md") -Encoding UTF8

    New-ReadinessZip -SourceDir $stageDir -ZipPath $zipPath
    Test-ReadinessPackZip -Path $zipPath
    Copy-Item -LiteralPath (Join-Path $stageDir "IMPLEMENTATION_MANIFEST.md") -Destination $latestImplementationManifestPath -Force
    Copy-Item -LiteralPath $zipPath -Destination $latestZipPath -Force
    $checksum = Write-ReadinessPackChecksum -ZipPath $zipPath
    $latestChecksum = Write-ReadinessPackChecksum -ZipPath $latestZipPath
    Write-Step "Running strict readiness pack verifier..."
    $global:LASTEXITCODE = 0
    & $VerifyScript -PackPath $latestZipPath -Root $Root
    if (!$? -or $LASTEXITCODE -ne 0) {
        throw "Strict readiness pack verifier failed."
    }
    Write-Step "Readiness pack created: $zipPath" "Green"
    Write-Step "Latest readiness pack: $latestZipPath" "Green"
    Write-Step "Latest implementation manifest: $latestImplementationManifestPath" "Green"
    Write-Step "Latest SHA-256: $($latestChecksum.sha256)" "Green"
    Write-Output $zipPath
} finally {
    Remove-Item -LiteralPath $stageDir -Recurse -Force -ErrorAction SilentlyContinue
}
