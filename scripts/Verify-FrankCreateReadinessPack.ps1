param(
    [string]$PackPath = "",
    [string]$Root = ""
)

$ErrorActionPreference = "Stop"

if (!$Root) {
    $Root = Resolve-Path (Join-Path $PSScriptRoot "..")
}

if (!$PackPath) {
    $PackPath = Join-Path $Root "user\frank_create\readiness_packs\frank-create-cliff-readiness-latest.zip"
}

function Write-Step {
    param([string]$Message, [string]$Color = "Magenta")
    Write-Host "[Frank Pack Verify] $Message" -ForegroundColor $Color
}

function Read-ZipText {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$EntryName
    )

    $entry = $Archive.GetEntry($EntryName)
    if ($null -eq $entry) {
        throw "Readiness pack ZIP is missing $EntryName."
    }

    $reader = New-Object System.IO.StreamReader($entry.Open())
    try {
        return $reader.ReadToEnd()
    } finally {
        $reader.Dispose()
    }
}

function Read-ZipBytes {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$EntryName
    )

    $entry = $Archive.GetEntry($EntryName)
    if ($null -eq $entry) {
        throw "Readiness pack ZIP is missing $EntryName."
    }

    $stream = $entry.Open()
    $memory = New-Object System.IO.MemoryStream
    try {
        $stream.CopyTo($memory)
        return $memory.ToArray()
    } finally {
        $memory.Dispose()
        $stream.Dispose()
    }
}

function Get-Sha256Hex {
    param([byte[]]$Bytes)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha256.ComputeHash($Bytes)
        return -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
    } finally {
        $sha256.Dispose()
    }
}

function Test-HandoffManifestMediaIntegrity {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [hashtable]$EntrySet,
        [array]$Assets,
        [string]$Label
    )

    foreach ($asset in @($Assets)) {
        $integrity = $asset.media_integrity
        $archivePath = [string]$asset.archive_path
        if (!$integrity -or !$integrity.sha256 -or !$integrity.file_size_bytes) {
            throw "Nested Cliff handoff manifest is missing $Label media_integrity."
        }
        if (!$archivePath -or !$EntrySet.ContainsKey($archivePath)) {
            throw "Nested Cliff handoff ZIP is missing $Label media file $archivePath."
        }

        $mediaBytes = Read-ZipBytes -Archive $Archive -EntryName $archivePath
        $expectedHash = ([string]$integrity.sha256).ToLowerInvariant()
        $actualHash = Get-Sha256Hex -Bytes $mediaBytes
        $expectedSize = [int64]$integrity.file_size_bytes
        if ($actualHash -ne $expectedHash -or [int64]$mediaBytes.Length -ne $expectedSize) {
            throw "Nested Cliff handoff manifest has $Label media integrity mismatch."
        }
    }
}

function Test-HandoffWorkflowBridge {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [hashtable]$EntrySet,
        [array]$Assets
    )

    foreach ($asset in @($Assets)) {
        $sidecarPath = [string]$asset.workflow_sidecar_path
        if (!$sidecarPath -or !$EntrySet.ContainsKey($sidecarPath)) {
            continue
        }

        $sidecar = Read-ZipText -Archive $Archive -EntryName $sidecarPath | ConvertFrom-Json
        $bridge = $sidecar.workflow_bridge
        if (!$bridge) {
            throw "Nested Cliff handoff workflow sidecar is missing workflow bridge metadata."
        }
        if (
            [string]$bridge.asset_id -ne [string]$asset.id -or
            $bridge.can_open_raw_canvas -ne $true -or
            @("api_prompt_attached", "receipt_only") -notcontains [string]$bridge.raw_canvas_load_status -or
            ([string]$bridge.raw_canvas_load_status -eq "api_prompt_attached" -and @($bridge.comfy_node_types).Count -lt 1) -or
            [string]$bridge.raw_canvas_url -notmatch "frankAssetId=" -or
            [string]$bridge.workflow_receipt_url -notmatch "/workflow"
        ) {
            throw "Nested Cliff handoff workflow bridge metadata is incomplete."
        }
    }
}

function Test-HandoffChannelExports {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [hashtable]$EntrySet,
        $Manifest
    )

    $channelExports = $Manifest.channel_exports
    if (!$channelExports -or [int]$Manifest.counts.channel_export_sets -lt 1 -or [int]$Manifest.counts.channel_export_files -lt 1) {
        throw "Nested Cliff handoff manifest is missing channel export metadata."
    }

    $requiredPresets = @(
        "pdp",
        "email-hero",
        "instagram-feed",
        "instagram-story",
        "paid-social",
        "transparent-png",
        "high-res-master"
    )
    $checkedFiles = 0
    foreach ($exportSetProperty in @($channelExports.PSObject.Properties)) {
        $exportSet = $exportSetProperty.Value
        if (!$exportSet.asset_id -or [int]$exportSet.preset_count -lt $requiredPresets.Count) {
            throw "Nested Cliff handoff channel export set metadata is incomplete."
        }
        foreach ($preset in $requiredPresets) {
            $exportProperty = $exportSet.exports.PSObject.Properties[$preset]
            $export = if ($exportProperty) { $exportProperty.Value } else { $null }
            if (!$export) {
                throw "Nested Cliff handoff channel export set is missing $preset."
            }
            $imageFile = [string]$export.image_file
            $metadataFile = [string]$export.metadata_file
            if (!$imageFile -or $imageFile -notlike "channel-exports/*/$preset/*" -or !$EntrySet.ContainsKey($imageFile)) {
                throw "Nested Cliff handoff ZIP is missing channel export image $imageFile."
            }
            if (!$metadataFile -or !$EntrySet.ContainsKey($metadataFile)) {
                throw "Nested Cliff handoff ZIP is missing channel export metadata $metadataFile."
            }
            $integrity = $export.media_integrity
            if (!$integrity -or !$integrity.sha256 -or !$integrity.file_size_bytes) {
                throw "Nested Cliff handoff channel export is missing media integrity metadata."
            }
            $mediaBytes = Read-ZipBytes -Archive $Archive -EntryName $imageFile
            $expectedHash = ([string]$integrity.sha256).ToLowerInvariant()
            $actualHash = Get-Sha256Hex -Bytes $mediaBytes
            if ($actualHash -ne $expectedHash -or [int64]$mediaBytes.Length -ne [int64]$integrity.file_size_bytes) {
                throw "Nested Cliff handoff channel export integrity mismatch."
            }
            $checkedFiles += 1
        }
    }
    if ($checkedFiles -lt $requiredPresets.Count) {
        throw "Nested Cliff handoff ZIP has no validated channel export files."
    }
}

if (!(Test-Path -LiteralPath $PackPath)) {
    throw "Readiness pack ZIP was not found: $PackPath"
}

$checksumPath = "$PackPath.sha256"
if (!(Test-Path -LiteralPath $checksumPath)) {
    throw "Readiness pack checksum sidecar was not found: $checksumPath"
}

$expectedHash = (Get-FileHash -LiteralPath $PackPath -Algorithm SHA256).Hash.ToLowerInvariant()
$sidecarText = Get-Content -LiteralPath $checksumPath -Raw
$sidecarHash = ($sidecarText.Split([char[]]" `t`r`n", [System.StringSplitOptions]::RemoveEmptyEntries) | Select-Object -First 1)
if ($sidecarHash -ne $expectedHash) {
    throw "Readiness pack checksum mismatch. Expected $expectedHash but sidecar has $sidecarHash."
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $PackPath).Path)
try {
    $entryNames = @($archive.Entries | ForEach-Object { $_.FullName })
    $entrySet = @{}
    foreach ($name in $entryNames) {
        $entrySet[$name.Replace("\", "/")] = $true
    }

    $requiredEntries = @(
        "OPEN_ME_FIRST.md",
        "IMPLEMENTATION_MANIFEST.md",
        "OPEN_FOR_CLIFF.md",
        "README.md",
        "FRANK_CREATE_CALL_DAY.md",
        "FRANK_CREATE_DEMO.md",
        "readiness-pack-manifest.json",
        "call-brief/frank-create-call-brief-latest.md",
        "provider-readiness/frank-create-provider-readiness-latest.md",
        "activation-checklist/frank-create-activation-checklist-latest.md",
        "brand-context/frank-create-brand-context-latest.md",
        "evidence/frank-create-demo-evidence-latest.md",
        "qa/browser-qa-receipt.json",
        "qa/shareable-pack-hygiene.json",
        "sync/frank-create-sync-manifest-latest.json",
        "setup/frank-create.env.example",
        "handoff-review/frank-create-review-board-latest.png",
        "launchers/CLIFF_START_HERE.cmd",
        "launchers/VERIFY_CLIFF_PACK.cmd",
        "screenshots/studio-live-desktop-latest.png",
        "screenshots/studio-live-mobile-latest.png",
        "screenshots/video-lab-live-desktop-latest.png",
        "screenshots/provider-audit-live-desktop-latest.png",
        "screenshots/graph-live-desktop-latest.png",
        "screenshots/graph-live-mobile-latest.png",
        "screenshots/raw-comfy-live-quiet-latest.png",
        "screenshots/raw-comfy-workflow-receipt-latest.png"
    )

    foreach ($name in $requiredEntries) {
        if (!$entrySet.ContainsKey($name)) {
            throw "Readiness pack ZIP is missing $name."
        }
    }

    $handoffEntryName = ($entrySet.Keys | Where-Object { $_ -like "handoffs/*.zip" } | Select-Object -First 1)
    if (!$handoffEntryName) {
        throw "Readiness pack ZIP is missing the nested Cliff handoff ZIP."
    }

    $manifest = Read-ZipText -Archive $archive -EntryName "readiness-pack-manifest.json" | ConvertFrom-Json
    $browserQa = Read-ZipText -Archive $archive -EntryName "qa/browser-qa-receipt.json" | ConvertFrom-Json
    $browserQaMarkdown = Read-ZipText -Archive $archive -EntryName "qa/browser-qa-receipt.md"
    $hygiene = Read-ZipText -Archive $archive -EntryName "qa/shareable-pack-hygiene.json" | ConvertFrom-Json
    $syncManifest = Read-ZipText -Archive $archive -EntryName "sync/frank-create-sync-manifest-latest.json" | ConvertFrom-Json
    $openMe = Read-ZipText -Archive $archive -EntryName "OPEN_ME_FIRST.md"
    $openForCliff = Read-ZipText -Archive $archive -EntryName "OPEN_FOR_CLIFF.md"
    $callDay = Read-ZipText -Archive $archive -EntryName "FRANK_CREATE_CALL_DAY.md"
    $demoRunbook = Read-ZipText -Archive $archive -EntryName "FRANK_CREATE_DEMO.md"
    $cliffLauncher = Read-ZipText -Archive $archive -EntryName "launchers/CLIFF_START_HERE.cmd"
    $packContextLaunchers = @(
        "CLIFF_START_HERE.cmd",
        "START_FRANK_CREATE_DEMO.cmd",
        "START_FRANK_CREATE.cmd",
        "CHECK_FRANK_CREATE.cmd",
        "VERIFY_CLIFF_PACK.cmd",
        "PREP_FRANK_CREATE_FOR_CLIFF.cmd",
        "BUILD_FRANK_CREATE_READINESS_PACK.cmd",
        "STOP_FRANK_CREATE.cmd"
    )
    $launcherTexts = @{}
    foreach ($launcherName in $packContextLaunchers) {
        $launcherTexts[$launcherName] = Read-ZipText -Archive $archive -EntryName "launchers/$launcherName"
    }
    $implementationManifest = Read-ZipText -Archive $archive -EntryName "IMPLEMENTATION_MANIFEST.md"
    $handoffBytes = Read-ZipBytes -Archive $archive -EntryName $handoffEntryName
    $handoffStream = New-Object System.IO.MemoryStream(,$handoffBytes)
    $handoffArchive = New-Object System.IO.Compression.ZipArchive($handoffStream, [System.IO.Compression.ZipArchiveMode]::Read)
    try {
        $handoffEntryNames = @($handoffArchive.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
        $handoffEntrySet = @{}
        foreach ($name in $handoffEntryNames) {
            $handoffEntrySet[$name] = $true
        }
        if (!$handoffEntrySet.ContainsKey("HANDOFF_SPEC.md")) {
            throw "Nested Cliff handoff ZIP is missing HANDOFF_SPEC.md."
        }
        $handoffManifest = Read-ZipText -Archive $handoffArchive -EntryName "frank-create-handoff.json" | ConvertFrom-Json
        Test-HandoffManifestMediaIntegrity -Archive $handoffArchive -EntrySet $handoffEntrySet -Assets $handoffManifest.approved_assets -Label "approved"
        Test-HandoffManifestMediaIntegrity -Archive $handoffArchive -EntrySet $handoffEntrySet -Assets $handoffManifest.reference_assets -Label "reference"
        Test-HandoffWorkflowBridge -Archive $handoffArchive -EntrySet $handoffEntrySet -Assets $handoffManifest.approved_assets
        Test-HandoffChannelExports -Archive $handoffArchive -EntrySet $handoffEntrySet -Manifest $handoffManifest
        $reviewBoard = $handoffManifest.review_board
        if (!$reviewBoard -or [string]$reviewBoard.archive_path -ne "review/frank-create-review-board.png") {
            throw "Nested Cliff handoff manifest is missing review board metadata."
        }
        if (!$handoffEntrySet.ContainsKey([string]$reviewBoard.archive_path)) {
            throw "Nested Cliff handoff ZIP is missing the review board PNG."
        }
        $reviewBoardBytes = Read-ZipBytes -Archive $handoffArchive -EntryName ([string]$reviewBoard.archive_path)
        if ($reviewBoardBytes.Length -lt 8 -or $reviewBoardBytes[0] -ne 0x89 -or $reviewBoardBytes[1] -ne 0x50 -or $reviewBoardBytes[2] -ne 0x4E -or $reviewBoardBytes[3] -ne 0x47) {
            throw "Nested Cliff handoff review board is not a PNG."
        }
        if ([int]$reviewBoard.approved_asset_count -lt 1 -or [int]$reviewBoard.width -lt 1200 -or [int]$reviewBoard.height -lt 800) {
            throw "Nested Cliff handoff review board metadata is incomplete."
        }
        $topLevelReviewBoardBytes = Read-ZipBytes -Archive $archive -EntryName "handoff-review/frank-create-review-board-latest.png"
        if ($topLevelReviewBoardBytes.Length -lt 8 -or $topLevelReviewBoardBytes[0] -ne 0x89 -or $topLevelReviewBoardBytes[1] -ne 0x50 -or $topLevelReviewBoardBytes[2] -ne 0x4E -or $topLevelReviewBoardBytes[3] -ne 0x47) {
            throw "Top-level Cliff handoff review board is not a PNG."
        }
        if ((Get-Sha256Hex -Bytes $topLevelReviewBoardBytes) -ne (Get-Sha256Hex -Bytes $reviewBoardBytes)) {
            throw "Top-level Cliff handoff review board does not match the nested handoff review board."
        }
    } finally {
        $handoffArchive.Dispose()
        $handoffStream.Dispose()
    }
    $providerTemplate = Read-ZipText -Archive $archive -EntryName "setup/frank-create.env.example"
    $providerReadiness = Read-ZipText -Archive $archive -EntryName "provider-readiness/frank-create-provider-readiness-latest.md"
    $providerReadinessJson = Read-ZipText -Archive $archive -EntryName "provider-readiness/frank-create-provider-readiness-latest.json" | ConvertFrom-Json
    $activationChecklist = Read-ZipText -Archive $archive -EntryName "activation-checklist/frank-create-activation-checklist-latest.md"
    $activationChecklistJson = Read-ZipText -Archive $archive -EntryName "activation-checklist/frank-create-activation-checklist-latest.json" | ConvertFrom-Json
    $brandContext = Read-ZipText -Archive $archive -EntryName "brand-context/frank-create-brand-context-latest.md"
    $brandContextJson = Read-ZipText -Archive $archive -EntryName "brand-context/frank-create-brand-context-latest.json" | ConvertFrom-Json
    $cliffPrep = Read-ZipText -Archive $archive -EntryName "receipts/cliff_prep_status.json" | ConvertFrom-Json
    if (!$cliffPrep.browser_qa -or $cliffPrep.browser_qa.status -ne "ready") {
        throw "Cliff prep receipt does not include ready browser QA."
    }
    $cliffBrowserQaKeys = @($cliffPrep.browser_qa.checks | ForEach-Object { $_.key })
    foreach ($key in @("studio_interactions", "demo_doctor_checksum", "studio_model_preflight", "studio_local_generate", "studio_masked_edit_generate", "video_lab", "provider_audit", "advanced_graph", "raw_comfy", "raw_comfy_receipt")) {
        if ($cliffBrowserQaKeys -notcontains $key) {
            throw "Cliff prep browser QA is missing $key."
        }
    }

    if ($manifest.browser_qa.status -ne "ready") {
        throw "Readiness pack manifest Browser QA is not ready."
    }
    if ($manifest.shareable_pack_hygiene.status -ne "clean") {
        throw "Readiness pack manifest hygiene is not clean."
    }
    if ($browserQa.status -ne "ready") {
        throw "Readiness pack Browser QA receipt is not ready."
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
        throw "Readiness pack Browser QA receipt does not distinguish browser-time checksum proof from the current readiness ZIP .sha256 sidecar."
    }
    $browserQaKeys = @($browserQa.checks | ForEach-Object { $_.key })
    foreach ($key in @("studio_interactions", "demo_doctor_checksum", "studio_model_preflight", "studio_local_generate", "studio_masked_edit_generate", "video_lab", "provider_audit")) {
        if ($browserQaKeys -notcontains $key) {
            throw "Readiness pack Browser QA receipt does not include $key."
        }
    }
    $modelPreflightCheck = @($browserQa.checks | Where-Object { $_.key -eq "studio_model_preflight" } | Select-Object -First 1)
    if (!$modelPreflightCheck -or $modelPreflightCheck.status -ne "ready" -or $modelPreflightCheck.detail -notmatch "no-spend selected model preflight" -or $modelPreflightCheck.detail -notmatch "safe payload preview") {
        throw "Readiness pack Browser QA receipt is missing selected model preflight proof."
    }
    $localGenerateCheck = @($browserQa.checks | Where-Object { $_.key -eq "studio_local_generate" } | Select-Object -First 1)
    if (!$localGenerateCheck -or $localGenerateCheck.status -ne "ready" -or $localGenerateCheck.detail -notmatch "local Studio Generate button created output assets") {
        throw "Readiness pack Browser QA receipt is missing local generate button proof."
    }
    $maskedEditGenerateCheck = @($browserQa.checks | Where-Object { $_.key -eq "studio_masked_edit_generate" } | Select-Object -First 1)
    if (!$maskedEditGenerateCheck -or $maskedEditGenerateCheck.status -ne "ready" -or $maskedEditGenerateCheck.detail -notmatch "masked edit Generate button created output assets") {
        throw "Readiness pack Browser QA receipt is missing masked edit button proof."
    }
    $videoLabCheck = @($browserQa.checks | Where-Object { $_.key -eq "video_lab" } | Select-Object -First 1)
    if (!$videoLabCheck -or $videoLabCheck.status -ne "included" -or $videoLabCheck.browser_status -ne "ready") {
        throw "Readiness pack Video Lab screenshot/browser proof is not ready."
    }
    $providerAuditCheck = @($browserQa.checks | Where-Object { $_.key -eq "provider_audit" } | Select-Object -First 1)
    if (!$providerAuditCheck -or $providerAuditCheck.status -ne "included") {
        throw "Readiness pack Provider Adapter Audit screenshot is not marked included."
    }
    if ($hygiene.status -ne "clean") {
        throw "Readiness pack hygiene receipt is not clean."
    }
    if ($syncManifest.schema_version -ne "frank-create.sync.v1") {
        throw "FrankHub sync manifest is missing schema version frank-create.sync.v1."
    }
    if (!$syncManifest.sync_contract -or $syncManifest.sync_contract.tables.assets -ne "frank_create_assets") {
        throw "FrankHub sync manifest is missing the assets table contract."
    }
    if ([int]$syncManifest.counts.approved_assets -lt 1 -or [int]$syncManifest.counts.reference_assets -lt 1) {
        throw "FrankHub sync manifest is missing approved/reference asset counts."
    }
    if (!$manifest.sync_manifest -or $manifest.sync_manifest.archive_path -ne "sync/frank-create-sync-manifest-latest.json") {
        throw "Readiness pack manifest is missing the packaged FrankHub sync manifest metadata."
    }
    if ($openMe -notmatch "CLIFF_START_HERE\.cmd") {
        throw "OPEN_ME_FIRST.md does not point to CLIFF_START_HERE.cmd."
    }
    if ($openMe -notmatch "sync/frank-create-sync-manifest-latest\.json" -or $openMe -notmatch "frank-create\.sync\.v1") {
        throw "OPEN_ME_FIRST.md does not mention the packaged FrankHub sync manifest."
    }
    if ($openForCliff -notmatch "browser QA receipt" -or $openForCliff -notmatch "painted mask saves") {
        throw "OPEN_FOR_CLIFF.md does not summarize the browser QA mask-save proof."
    }
    if ($openForCliff -notmatch "QA-created mask assets and files are cleaned up afterward") {
        throw "OPEN_FOR_CLIFF.md does not mention browser QA mask cleanup."
    }
    if ($openForCliff -notmatch "safe provider key plan" -or $openForCliff -notmatch "env-var names" -or $openForCliff -notmatch "no provider secrets") {
        throw "OPEN_FOR_CLIFF.md does not summarize the browser QA provider key-plan copy proof."
    }
    if ($openForCliff -notmatch "Gemini, OpenAI, and Replicate") {
        throw "OPEN_FOR_CLIFF.md does not summarize the Provider Setup launch-order proof."
    }
    if ($openForCliff -notmatch "no-spend selected model preflight" -or $openForCliff -notmatch "safe payload preview") {
        throw "OPEN_FOR_CLIFF.md does not summarize the selected-model preflight proof."
    }
    if ($openForCliff -notmatch "local Studio Generate button" -or $openForCliff -notmatch "Local Comfy selected") {
        throw "OPEN_FOR_CLIFF.md does not summarize the local Generate proof."
    }
    if ($openForCliff -notmatch "masked edit Generate button" -or $openForCliff -notmatch "painted mask") {
        throw "OPEN_FOR_CLIFF.md does not summarize the masked-edit Generate proof."
    }
    if ($openForCliff -notmatch "Open review board" -or $openForCliff -notmatch "direct visual review-board PNG") {
        throw "OPEN_FOR_CLIFF.md does not summarize the direct review-board proof."
    }
    if ($openForCliff -notmatch "Open sync manifest" -or $openForCliff -notmatch "frank-create\.sync\.v1") {
        throw "OPEN_FOR_CLIFF.md does not summarize the FrankHub sync manifest proof."
    }
    if ($openForCliff -notmatch "safe selected-output run brief" -or $openForCliff -notmatch "workflow JSON sidecar" -or $openForCliff -notmatch "workflow provenance") {
        throw "OPEN_FOR_CLIFF.md does not summarize the browser QA run-brief copy proof."
    }
    if ($callDay -notmatch "Paint edit mask" -or $callDay -notmatch "mask painter save" -or $callDay -notmatch "Copy key plan" -or $callDay -notmatch "Open review board" -or $callDay -notmatch "Copy run brief" -or $callDay -notmatch "Download workflow JSON") {
        throw "FRANK_CREATE_CALL_DAY.md does not include the selective-retouch and run-brief browser QA talk track."
    }
    if ($callDay -notmatch "Gemini, OpenAI, and Replicate") {
        throw "FRANK_CREATE_CALL_DAY.md does not include the Provider Setup three-provider talk track."
    }
    if ($callDay -notmatch "Check selected model" -or $callDay -notmatch "no-spend selected model preflight") {
        throw "FRANK_CREATE_CALL_DAY.md does not include the selected-model preflight talk track."
    }
    if ($callDay -notmatch "local Studio Generate button" -or $callDay -notmatch "masked edit Generate button") {
        throw "FRANK_CREATE_CALL_DAY.md does not include the local Generate and masked-edit Generate proof talk track."
    }
    if ($demoRunbook -notmatch "proves the visible Studio path in browser QA") {
        throw "FRANK_CREATE_DEMO.md does not describe the visible Studio browser QA proof."
    }
    if ($demoRunbook -notmatch "three-provider Cliff launch plan") {
        throw "FRANK_CREATE_DEMO.md does not describe the Provider Setup three-provider proof."
    }
    foreach ($envVar in @(
        '$env:GOOGLE_API_KEY',
        '$env:OPENAI_API_KEY',
        '$env:REPLICATE_API_TOKEN'
    )) {
        if ($demoRunbook -notmatch [regex]::Escape($envVar)) {
            throw "FRANK_CREATE_DEMO.md does not list all Cliff pack provider env vars."
        }
    }
    if ($demoRunbook -notmatch "Copy run brief" -or $demoRunbook -notmatch "Download workflow JSON" -or $demoRunbook -notmatch "safe selected-output run brief") {
        throw "FRANK_CREATE_DEMO.md does not describe the selected-output run-brief proof."
    }
    if ($cliffLauncher -notmatch "frank-create-demo-evidence-latest\.md") {
        throw "Packaged CLIFF_START_HERE.cmd does not open the latest demo evidence receipt."
    }
    if ($cliffLauncher -notmatch "readiness-pack-manifest\.json") {
        throw "Packaged CLIFF_START_HERE.cmd does not detect extracted readiness-pack context."
    }
    if ($cliffLauncher -notmatch "Opening packaged proof docs") {
        throw "Packaged CLIFF_START_HERE.cmd does not explain extracted-pack proof-doc mode."
    }
    foreach ($launcherName in $packContextLaunchers) {
        $launcherText = $launcherTexts[$launcherName]
        if ($launcherText -notmatch "readiness-pack-manifest\.json" -or $launcherText -notmatch "Opening packaged proof docs") {
            throw "Packaged $launcherName does not guard extracted readiness-pack context."
        }
    }
    if ($cliffLauncher -notmatch "frank-create-implementation-manifest-latest\.md") {
        throw "Packaged CLIFF_START_HERE.cmd does not open the implementation manifest."
    }
    if ($cliffLauncher -notmatch "frank-create-call-brief-latest\.md") {
        throw "Packaged CLIFF_START_HERE.cmd does not open the latest call brief."
    }
    if ($cliffLauncher -notmatch "frank-create-provider-readiness-latest\.md") {
        throw "Packaged CLIFF_START_HERE.cmd does not open the provider-readiness receipt."
    }
    if ($cliffLauncher -notmatch "frank-create-activation-checklist-latest\.md") {
        throw "Packaged CLIFF_START_HERE.cmd does not open the activation checklist."
    }
    if ($cliffLauncher -notmatch "frank-create-brand-context-latest\.md") {
        throw "Packaged CLIFF_START_HERE.cmd does not open the brand-context receipt."
    }
    if (@($manifest.includes) -notcontains "activation-checklist/frank-create-activation-checklist-latest.md") {
        throw "Readiness pack manifest does not include the activation checklist."
    }
    if (@($manifest.includes) -notcontains "brand-context/frank-create-brand-context-latest.md") {
        throw "Readiness pack manifest does not include the brand-context receipt."
    }
    if ($openMe -notmatch "frank-create-activation-checklist-latest\.md") {
        throw "OPEN_ME_FIRST.md does not point to the activation checklist."
    }
    if ($openMe -notmatch "frank-create-brand-context-latest\.md") {
        throw "OPEN_ME_FIRST.md does not point to the brand-context receipt."
    }
    if ($implementationManifest -notmatch "Frank Create Implementation Manifest") {
        throw "Implementation manifest title is missing."
    }
    if ($implementationManifest -notmatch "Conversational Image Studio") {
        throw "Implementation manifest does not describe the Studio surface."
    }
    if ($implementationManifest -notmatch "paints and saves a mask into the masked-edit composer") {
        throw "Implementation manifest does not prove the visible Studio mask-save browser QA path."
    }
    if ($implementationManifest -notmatch "cleans QA mask assets/files") {
        throw "Implementation manifest does not prove browser QA mask cleanup."
    }
    if ($implementationManifest -notmatch "copies a safe provider key plan with env-var names and no secret values") {
        throw "Implementation manifest does not prove the visible Studio provider key-plan copy path."
    }
    if ($implementationManifest -notmatch "copies a safe selected-output run brief with workflow provenance") {
        throw "Implementation manifest does not prove the visible Studio run-brief copy path."
    }
    if ($implementationManifest -notmatch "downloads a safe workflow JSON sidecar with workflow provenance") {
        throw "Implementation manifest does not prove the visible Studio workflow JSON download path."
    }
    if ($implementationManifest -notmatch "No-spend adapter audit:\s+5 / 5 launch runners") {
        throw "Implementation manifest does not prove the no-spend adapter audit."
    }
    if ($implementationManifest -notmatch "Frank Body Mode \+ brand context" -or $implementationManifest -notmatch "Brand-context brief packaged with") {
        throw "Implementation manifest does not prove Frank Body Mode brand-context readiness."
    }
    if ($implementationManifest -notmatch "Production activation checklist" -or $implementationManifest -notmatch "Activation checklist packaged with") {
        throw "Implementation manifest does not prove the production activation checklist."
    }
    if ($implementationManifest -notmatch "CLIFF_START_HERE\.cmd") {
        throw "Implementation manifest does not list the call-day launcher."
    }
    foreach ($asset in @($handoffManifest.approved_assets)) {
        if (!$asset.workflow_provenance) {
            throw "Nested Cliff handoff manifest is missing approved workflow provenance."
        }
    }
    $proofAssets = @($handoffManifest.proof_assets | Where-Object { $_ })
    foreach ($asset in $proofAssets) {
        if (!$asset.workflow_provenance) {
            throw "Nested Cliff handoff manifest is missing proof workflow provenance."
        }
        $archivePath = [string]$asset.archive_path
        if (!$archivePath -or !$handoffEntrySet.ContainsKey($archivePath)) {
            throw "Nested Cliff handoff ZIP is missing proof media file."
        }
    }
    $workflowSidecarEntries = @($handoffEntrySet.Keys | Where-Object { $_ -like "workflows/*.json" })
    if ($workflowSidecarEntries.Count -lt 1) {
        throw "Nested Cliff handoff ZIP is missing approved workflow sidecar JSON files."
    }
    foreach ($asset in @($handoffManifest.approved_assets)) {
        $sidecarPath = [string]$asset.workflow_sidecar_path
        if (!$sidecarPath) {
            throw "Nested Cliff handoff manifest is missing approved workflow_sidecar_path."
        }
        if (!$handoffEntrySet.ContainsKey($sidecarPath)) {
            throw "Nested Cliff handoff ZIP is missing workflow sidecar $sidecarPath."
        }
    }
    foreach ($asset in $proofAssets) {
        $sidecarPath = [string]$asset.workflow_sidecar_path
        if (!$sidecarPath) {
            throw "Nested Cliff handoff manifest is missing proof workflow_sidecar_path."
        }
        if (!$handoffEntrySet.ContainsKey($sidecarPath)) {
            throw "Nested Cliff handoff ZIP is missing workflow sidecar $sidecarPath."
        }
    }
    if ($providerTemplate -match "sk-|r8_") {
        throw "Provider template contains a provider-token-shaped value."
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
    if ($providerReadiness -notmatch "## No-Spend Adapter Audit") {
        throw "Provider readiness receipt is missing the No-Spend Adapter Audit section."
    }
    if ($providerReadiness -notmatch "Adapter runners registered:\s+5 / 5") {
        throw "Provider readiness receipt does not prove all launch adapters are registered."
    }
    if ($providerReadiness -notmatch "External API calls made:\s+no") {
        throw "Provider readiness receipt does not prove the adapter audit was no-spend."
    }
    if ($providerReadiness -notmatch "Secret values returned:\s+no") {
        throw "Provider readiness receipt does not prove secret values were withheld."
    }
    if ($providerReadiness -notmatch "Operation request previews:\s+\d+\s+checked\s+/\s+0\s+failures") {
        throw "Provider readiness receipt is missing operation request preview proof."
    }
    if ([int]($providerReadinessJson.adapter_audit.summary.operation_preview_count) -lt 12 -or [int]($providerReadinessJson.adapter_audit.summary.operation_preview_failures) -ne 0) {
        throw "Provider readiness JSON is missing operation request preview proof."
    }
    if ($providerReadiness -notmatch "## Mocked Live-Path Coverage") {
        throw "Provider readiness receipt is missing mocked live-path coverage."
    }
    if ($providerReadiness -notmatch "send edit sources as inline data") {
        throw "Provider readiness receipt does not prove Google/Nano Banana edit-source inline data coverage."
    }
    if ($providerReadiness -notmatch "server-side Replicate token path") {
        throw "Provider readiness receipt does not prove Replicate live-path coverage."
    }
    if (@($providerReadinessJson.mocked_live_path_coverage).Count -lt 3) {
        throw "Provider readiness JSON does not include mocked live-path coverage for all launch adapters."
    }
    if ($activationChecklist -notmatch "Frank Create Production Unlock Checklist" -or $activationChecklist -notmatch "Paste rotated live provider keys") {
        throw "Activation checklist receipt is missing production unlock actions."
    }
    if ($activationChecklist -notmatch "Rotate the exposed Replicate token") {
        throw "Activation checklist receipt is missing the exposed Replicate token rotation step."
    }
    if (@($activationChecklistJson.steps).Count -lt 4) {
        throw "Activation checklist JSON does not include the production unlock steps."
    }
    if ($activationChecklist -match "server-side-openai-secret|server-side-replicate|r8_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,}") {
        throw "Activation checklist contains a provider secret shaped value."
    }
    if ($brandContext -notmatch "Frank Create Brand Context Brief") {
        throw "Brand context receipt title is missing."
    }
    if ($brandContext -notmatch "Prompt-guided target" -or $brandContext -notmatch "Future LoRA target") {
        throw "Brand context receipt does not explain prompt-guided and LoRA readiness."
    }
    if ($brandContext -notmatch "Do Not Train On" -or $brandContext -notmatch "rights clearance") {
        throw "Brand context receipt does not include future training guardrails."
    }
    if ([int]$brandContextJson.summary.reference_asset_count -lt 1) {
        throw "Brand context JSON does not include at least one reference asset."
    }
    if (!$brandContextJson.training_recommendation.lora) {
        throw "Brand context JSON is missing the LoRA recommendation."
    }
    if (!$cliffPrep.provider_adapter_audit) {
        throw "Cliff prep receipt is missing provider_adapter_audit."
    }
    if ([int]$cliffPrep.provider_adapter_audit.runner_registered -ne [int]$cliffPrep.provider_adapter_audit.model_count) {
        throw "Cliff prep provider audit does not prove all launch runners are registered."
    }
    if ([int]$cliffPrep.provider_adapter_audit.preview_failures -ne 0) {
        throw "Cliff prep provider audit has request-preview failures."
    }
    if (-not [bool]$cliffPrep.provider_adapter_audit.no_spend) {
        throw "Cliff prep provider audit does not prove no-spend mode."
    }
    if ([bool]$cliffPrep.provider_adapter_audit.secret_values_returned) {
        throw "Cliff prep provider audit reported secret values."
    }

    Write-Step "Readiness pack verified: $(Split-Path -Leaf $PackPath)" "Green"
    Write-Step "SHA-256: $expectedHash" "Green"
    Write-Step "Entries: $($entryNames.Count); screenshots: $($manifest.screenshot_count); launchers: $(@($entrySet.Keys | Where-Object { $_ -like 'launchers/*.cmd' }).Count)" "Green"
} finally {
    $archive.Dispose()
}
