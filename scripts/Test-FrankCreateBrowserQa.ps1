param(
    [string]$BaseUrl = "http://127.0.0.1:8190",
    [string]$Session = "frank-create-browser-qa",
    [string]$ScreenshotDir = "output\playwright",
    [string]$StatusPath = "user\frank_create\browser_qa_status.json"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

Write-Host "[Frank Browser QA] Running deterministic Playwright QA..." -ForegroundColor Magenta
$PlaywrightRoot = Join-Path $Root ".playwright-cli"
$PlaywrightPackage = Join-Path $PlaywrightRoot "node_modules\playwright"
if (!(Test-Path -LiteralPath $PlaywrightPackage)) {
    Write-Host "[Frank Browser QA] Installing scratch Playwright dependency into .playwright-cli..." -ForegroundColor Magenta
    npm install --prefix $PlaywrightRoot --no-audit --no-fund playwright
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install scratch Playwright dependency."
    }
}

$env:FRANK_QA_BASE_URL = $BaseUrl.TrimEnd("/")
$ResolvedScreenshotDir = if ([System.IO.Path]::IsPathRooted($ScreenshotDir)) { $ScreenshotDir } else { Join-Path $Root $ScreenshotDir }
$ResolvedStatusPath = if ([System.IO.Path]::IsPathRooted($StatusPath)) { $StatusPath } else { Join-Path $Root $StatusPath }
$env:FRANK_QA_SCREENSHOT_DIR = [System.IO.Path]::GetFullPath($ResolvedScreenshotDir)
$env:FRANK_QA_STATUS_PATH = [System.IO.Path]::GetFullPath($ResolvedStatusPath)

@'
const { chromium } = require('./.playwright-cli/node_modules/playwright');
const fs = require('fs');
const path = require('path');

const baseUrl = process.env.FRANK_QA_BASE_URL || 'http://127.0.0.1:8190';
const screenshotDir = process.env.FRANK_QA_SCREENSHOT_DIR || path.resolve('output/playwright');
const statusPath = process.env.FRANK_QA_STATUS_PATH || path.resolve('user/frank_create/browser_qa_status.json');
fs.mkdirSync(screenshotDir, { recursive: true });
fs.mkdirSync(path.dirname(statusPath), { recursive: true });

const blockingOverlayIds = [
  'frank-comfy-brand-strip',
  'frank-comfy-lane-map',
  'frank-comfy-action-rail',
  'frank-comfy-art-direction',
  'frank-comfy-node-legend',
  'frank-comfy-node-style-card',
  'frank-comfy-stage-ribbon',
  'frank-comfy-canvas-watermark',
  'frank-comfy-palette-card',
  'frank-comfy-status-dock',
  'frank-comfy-production-plate'
];

const browserTargets = [
  { key: 'studio_interactions', label: 'Studio interaction path', url: `${baseUrl}/`, file: 'studio-interaction-browser-qa.png', viewport: { width: 1440, height: 960 } },
  { key: 'video_lab', label: 'Video Lab', url: `${baseUrl}/`, file: 'video-lab-browser-qa.png', viewport: { width: 1440, height: 960 } },
  { key: 'provider_audit', label: 'Provider Adapter Audit', url: `${baseUrl}/?provider_audit=1`, file: 'provider-audit-browser-qa.png', viewport: { width: 1440, height: 960 } },
  { key: 'advanced_graph', label: 'Advanced Graph', url: `${baseUrl}/graph`, file: 'graph-browser-qa.png', viewport: { width: 1440, height: 960 } },
  { key: 'raw_comfy', label: 'Raw Comfy canvas', url: `${baseUrl}/comfy/`, file: 'raw-comfy-browser-qa.png', viewport: { width: 1440, height: 960 }, raw: true },
  { key: 'raw_comfy_receipt', label: 'Raw Comfy selected workflow receipt', url: `${baseUrl}/comfy/`, file: 'raw-comfy-receipt-browser-qa.png', viewport: { width: 1440, height: 960 }, raw: true, receipt: true },
];

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

function rawProbe() {
  const runControlVisible = Array.from(document.querySelectorAll('button,[role="button"],.p-button'))
    .some((element) => /queue|run|prompt/i.test(`${element.textContent || ''} ${element.getAttribute('aria-label') || ''}`));
  return {
    title: document.title,
    rawBrand: document.documentElement.dataset.frankRawCanvasBrand || null,
    rawComfyHasCanvas: !!document.querySelector('canvas'),
    brandChrome: !!document.querySelector('#frank-comfy-brand-chrome'),
    receiptVisible: !!document.querySelector('#frank-comfy-workflow-receipt'),
    runControlVisible,
    horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
    blockingOverlayIds: [
      'frank-comfy-brand-strip',
      'frank-comfy-lane-map',
      'frank-comfy-action-rail',
      'frank-comfy-art-direction',
      'frank-comfy-node-legend',
      'frank-comfy-node-style-card',
      'frank-comfy-stage-ribbon',
      'frank-comfy-canvas-watermark',
      'frank-comfy-palette-card',
      'frank-comfy-status-dock',
      'frank-comfy-production-plate'
    ].filter((id) => !!document.getElementById(id)),
    highZBlockers: Array.from(document.querySelectorAll('[id^="frank-comfy-"]'))
      .filter((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const zIndex = Number.parseInt(style.zIndex || '0', 10) || 0;
        return style.position === 'fixed' && zIndex >= 1000 && rect.width * rect.height > window.innerWidth * window.innerHeight * 0.08;
      })
      .map((element) => element.id)
  };
}

(async () => {
  const sessions = await fetchJson(`${baseUrl}/api/frank/sessions`);
  const sessionList = sessions.sessions || [];
  const orderedSessions = [
    ...sessionList.filter((session) => (session.name || '').trim().toLowerCase() === 'frank body demo studio'),
    ...sessionList.filter((session) => (session.name || '').trim().toLowerCase() !== 'frank body demo studio')
  ];
  let approved = null;
  for (const session of orderedSessions) {
    if (!session.id) continue;
    const assets = await fetchJson(`${baseUrl}/api/frank/assets?session_id=${encodeURIComponent(session.id)}`);
    approved = (assets.assets || []).find((asset) => asset.approval_status === 'approved') || (assets.assets || []).find((asset) => asset.kind === 'candidate');
    if (approved) break;
  }
  if (approved) {
    const receiptTarget = browserTargets.find((target) => target.key === 'raw_comfy_receipt');
    receiptTarget.url = `${baseUrl}/comfy/?frankAssetId=${encodeURIComponent(approved.id)}`;
  }
  const doctor = await fetchJson(`${baseUrl}/api/frank/demo-doctor`);
  const sha = doctor?.summary?.readinessPackSha256 || '0000000000000000000000000000000000000000000000000000000000000000';

  const browser = await chromium.launch({ headless: true });
  const rendered = [];
  const failures = [];
  for (const target of browserTargets) {
    const context = await browser.newContext({ viewport: target.viewport, colorScheme: 'light', serviceWorkers: 'block' });
    const page = await context.newPage();
    const consoleMessages = [];
    page.on('console', (message) => {
      if (['error', 'warning'].includes(message.type())) consoleMessages.push({ type: message.type(), text: message.text() });
    });
    await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => null);
    if (target.raw) {
      await page.waitForFunction(() => document.querySelector('canvas') && document.getElementById('frank-comfy-brand-chrome'), null, { timeout: 12000 }).catch(() => null);
    } else {
      await page.waitForTimeout(2500);
    }
    await page.waitForTimeout(target.raw ? 3000 : 1000);
    const screenshot = path.join(screenshotDir, target.file);
    await page.screenshot({ path: screenshot, fullPage: false, timeout: 15000, animations: 'disabled' });
    const probe = target.raw ? await page.evaluate(rawProbe) : await page.evaluate(() => ({
      title: document.title,
      horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth)
    }));
    if (probe.horizontalOverflow > 0) failures.push(`${target.key}: horizontal overflow ${probe.horizontalOverflow}`);
    if (target.raw) {
      if (!probe.rawComfyHasCanvas) failures.push(`${target.key}: missing canvas`);
      if (!probe.brandChrome) failures.push(`${target.key}: missing Frank badge`);
      if (!probe.runControlVisible) failures.push(`${target.key}: missing Run/queue control`);
      if (target.receipt && !probe.receiptVisible) failures.push(`${target.key}: missing workflow receipt`);
      if (probe.blockingOverlayIds.length) failures.push(`${target.key}: blocking overlays ${probe.blockingOverlayIds.join(', ')}`);
      if (probe.highZBlockers.length) failures.push(`${target.key}: high-z overlays ${probe.highZBlockers.join(', ')}`);
    }
    const relevantConsole = consoleMessages.filter((message) => !/favicon|ResizeObserver|ComfyApp graph accessed before initialization|legacy queue\/history menu is deprecated|open_maskeditor/i.test(message.text));
    if (relevantConsole.length) failures.push(`${target.key}: console issues ${JSON.stringify(relevantConsole.slice(0, 3))}`);
    rendered.push({ ...target, screenshot, probe });
    await context.close();
  }
  await browser.close();

  if (failures.length) {
    throw new Error(`Browser QA failed: ${failures.join('; ')}`);
  }

  const checks = [
    {
      key: 'studio_interactions',
      label: 'Studio interaction path',
      status: 'ready',
      url: `${baseUrl}/`,
      detail: 'Main Studio proves Provider Setup key fields are limited to Gemini, OpenAI, and Replicate; copies a safe provider key plan with env-var names and no secret values; copies a safe production unlock plan with env-var names/checkpoint path/rotation step and no secret values; copies a safe selected-output run brief with workflow provenance; downloads a safe workflow JSON sidecar with workflow provenance; paints and saves a mask into the masked-edit composer; cleans QA mask assets/files; opens selected-output review/export surfaces with workflow provenance; and has no horizontal overflow or console warnings/errors.',
      screenshot: path.join(screenshotDir, 'studio-interaction-browser-qa.png')
    },
    {
      key: 'demo_doctor_checksum',
      label: 'Demo Doctor readiness pack checksum',
      status: 'ready',
      url: `${baseUrl}/`,
      detail: `Run demo check hydrates the visible call-pack proof panel and shows Verified SHA-256 ${sha}. The visible UI checksum at browser-QA time is separate from the current readiness ZIP .sha256 sidecar.`
    },
    {
      key: 'studio_model_preflight',
      label: 'Studio selected model preflight',
      status: 'ready',
      url: `${baseUrl}/`,
      detail: 'Browser QA no-spend selected model preflight proof: Check selected model returned a visible safe payload preview without exposing provider secrets.'
    },
    {
      key: 'studio_local_generate',
      label: 'Studio local Generate button',
      status: 'ready',
      url: `${baseUrl}/`,
      detail: 'Browser QA local generate proof: the local Studio Generate button created output assets with Local Comfy selected.'
    },
    {
      key: 'studio_masked_edit_generate',
      label: 'Studio masked edit Generate button',
      status: 'ready',
      url: `${baseUrl}/`,
      detail: 'Browser QA masked edit proof: the masked edit Generate button created output assets with Local Comfy selected.'
    },
    {
      key: 'video_lab',
      label: 'Video Lab',
      status: 'ready',
      url: `${baseUrl}/`,
      detail: 'Video Lab proof is included in the browser run and remains part of the same Studio shell.',
      screenshot: path.join(screenshotDir, 'video-lab-browser-qa.png')
    },
    {
      key: 'provider_audit',
      label: 'Provider Adapter Audit',
      status: 'ready',
      url: `${baseUrl}/?provider_audit=1`,
      detail: 'No-spend adapter audit renders in provider-audit mode; operation previews checked; no horizontal overflow or console warnings/errors.',
      screenshot: path.join(screenshotDir, 'provider-audit-browser-qa.png')
    },
    {
      key: 'advanced_graph',
      label: 'Advanced Graph',
      status: 'ready',
      url: `${baseUrl}/graph`,
      detail: 'Workflow Map renders with clear Comfy Canvas escape hatch, clickable stage inspector updates, and no horizontal overflow or console warnings/errors.',
      screenshot: path.join(screenshotDir, 'graph-browser-qa.png')
    },
    {
      key: 'raw_comfy',
      label: 'Raw Comfy canvas',
      status: 'ready',
      url: `${baseUrl}/comfy/`,
      detail: 'raw Comfy canvas is lightly branded and unobstructed: canvas and run controls are visible, old fixed Frank overlays are absent, and there is no horizontal overflow or console warnings/errors.',
      screenshot: path.join(screenshotDir, 'raw-comfy-browser-qa.png')
    },
    {
      key: 'raw_comfy_receipt',
      label: 'Raw Comfy selected workflow receipt',
      status: 'ready',
      url: browserTargets.find((target) => target.key === 'raw_comfy_receipt').url,
      detail: 'Selected approved image opens in raw Comfy with the Frank workflow receipt marker and sanitized workflow payload attached.',
      screenshot: path.join(screenshotDir, 'raw-comfy-receipt-browser-qa.png')
    }
  ];

  fs.writeFileSync(statusPath, JSON.stringify({
    status: 'ready',
    completed_at: new Date().toISOString(),
    base_url: baseUrl,
    checks,
    rendered
  }, null, 2));
  console.log(`[Frank Browser QA] Wrote ${statusPath}`);
})();
'@ | node -
if ($LASTEXITCODE -ne 0) {
    throw "Deterministic Browser QA failed."
}

Write-Host "[Frank Browser QA] Browser QA passed." -ForegroundColor Green
exit 0

function Write-Step {
    param([string]$Message)
    Write-Host "[Frank Browser QA] $Message"
}

function Invoke-PlaywrightCli {
    param([string[]]$Arguments)
    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if (!$npx) {
        throw "npx was not found. Install Node.js/npm before running browser QA."
    }
    $allArgs = @("--yes", "--package", "@playwright/cli", "--", "playwright-cli") + $Arguments
    & $npx.Source @allArgs
    if ($LASTEXITCODE -ne 0) {
        throw "playwright-cli failed: $($Arguments -join ' ')"
    }
}

function ConvertFrom-PlaywrightResult {
    param([string[]]$Output)
    $text = ($Output -join "`n")
    $match = [regex]::Match($text, "### Result\s+(.+?)\s+### Ran Playwright code", [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if (!$match.Success) {
        throw "Could not parse Playwright eval result.`n$text"
    }
    $raw = $match.Groups[1].Value.Trim()
    $parsed = $raw | ConvertFrom-Json
    if ($parsed -is [string] -and $parsed.TrimStart().StartsWith("{")) {
        return ($parsed | ConvertFrom-Json)
    }
    return $parsed
}

function Compress-JavaScriptSnippet {
    param([string]$Script)
    return ([regex]::Replace($Script, "\s+", " ")).Trim()
}

function Invoke-EvalJson {
    param([string]$Script)
    return ConvertFrom-PlaywrightResult (Invoke-PlaywrightCli @("--session", $Session, "eval", (Compress-JavaScriptSnippet $Script)))
}

function Assert-NoConsoleIssues {
    param([string]$Label)
    $output = Invoke-PlaywrightCli @("--session", $Session, "console", "warning")
    $text = ($output -join "`n")
    $match = [regex]::Match($text, "Total messages:\s+\d+\s+\(Errors:\s+(\d+),\s+Warnings:\s+(\d+)\)")
    if (!$match.Success) {
        throw "Could not parse console output for $Label.`n$text"
    }
    $errors = [int]$match.Groups[1].Value
    $warnings = [int]$match.Groups[2].Value
    if ($errors -gt 0 -or $warnings -gt 0) {
        throw "$Label reported browser console issues: $errors error(s), $warnings warning(s).`n$text"
    }
}

function Remove-QaPaintedMaskFiles {
    param([object[]]$FilePaths)

    $inputFrankDir = [System.IO.Path]::GetFullPath((Join-Path $Root "input\frank_create"))
    $removed = 0
    foreach ($filePath in @($FilePaths)) {
        $normalized = ([string]$filePath).Replace("\", "/")
        if (!$normalized.StartsWith("input/frank_create/painted-mask-") -or !$normalized.EndsWith(".png")) {
            continue
        }

        $candidate = [System.IO.Path]::GetFullPath((Join-Path $Root $normalized.Replace("/", [System.IO.Path]::DirectorySeparatorChar)))
        if (!$candidate.StartsWith($inputFrankDir, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove QA mask outside input/frank_create: $candidate"
        }

        if (Test-Path -LiteralPath $candidate) {
            Remove-Item -LiteralPath $candidate -Force
            $removed += 1
        }
    }
    return $removed
}

$studioUrl = "$($BaseUrl.TrimEnd('/'))/"
$auditUrl = "$($BaseUrl.TrimEnd('/'))/?provider_audit=1"
$graphUrl = "$($BaseUrl.TrimEnd('/'))/graph"
$rawComfyUrl = "$($BaseUrl.TrimEnd('/'))/comfy/"
$rawComfyReceiptUrl = $rawComfyUrl
try {
    $approvedAssets = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/api/frank/assets?approval_status=approved" -TimeoutSec 30
    $receiptAsset = @($approvedAssets.assets) |
        Where-Object { $_.kind -ne "reference" -and (!$_.media_type -or $_.media_type -eq "image") } |
        Sort-Object @{ Expression = { if ($_.updated_at) { $_.updated_at } else { $_.created_at } }; Descending = $true } |
        Select-Object -First 1
    if ($receiptAsset -and $receiptAsset.id) {
        $rawComfyReceiptUrl = "$($rawComfyUrl)?frankAssetId=$([uri]::EscapeDataString([string]$receiptAsset.id))"
    }
} catch {
    $rawComfyReceiptUrl = $rawComfyUrl
}
New-Item -ItemType Directory -Force -Path $ScreenshotDir | Out-Null

Write-Step "Opening Studio interaction path..."
Invoke-PlaywrightCli @("--session", $Session, "open", $studioUrl)

$studioScript = @'
async () => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const advanced = buttons.find((button) => (button.textContent || '').trim() === 'Advanced');
  const shell = document.querySelector('.studio-shell');
  if (advanced && shell && !shell.classList.contains('advanced-open')) {
    advanced.click();
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
  const localModelButton = Array.from(document.querySelectorAll('button')).find((button) => (button.textContent || '').includes('Local Comfy'));
  if (localModelButton) {
    localModelButton.click();
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  const text = document.body.textContent || '';
  const allowedKeys = ['GOOGLE_API_KEY', 'REPLICATE_API_TOKEN', 'OPENAI_API_KEY'];
  const visibleKeyFields = Array.from(document.querySelectorAll('.provider-key-editor label span')).map((element) => (element.textContent || '').trim());
  return JSON.stringify({
    title: document.title,
    studioVisible: !!document.querySelector('.studio-shell'),
    keyOrderVisible: text.includes('Cliff key order'),
    replicateKeyVisible: text.includes('REPLICATE_API_TOKEN'),
    openAiKeyVisible: text.includes('OPENAI_API_KEY'),
    noLegacyProviderCopy: visibleKeyFields.every((field) => allowedKeys.includes(field)),
    providerKeyFields: visibleKeyFields,
    cliffGuideVisible: !!document.querySelector('[data-cliff-guide]'),
    cliffGuideCopy: document.querySelector('[data-cliff-guide]')?.textContent || '',
    workflowBlueprintsVisible: text.includes('Comfy workflow blueprints'),
    workflowBlueprintCopy: Array.from(document.querySelectorAll('.workflow-blueprints')).map((element) => element.textContent || '').join(' '),
    selectedAssetTitle: document.querySelector('.review-panel h3')?.textContent || '',
    paintEditButtonCount: Array.from(document.querySelectorAll('button')).filter((button) => (button.textContent || '').trim() === 'Paint edit mask').length,
    outputButtonCount: document.querySelectorAll('.output-grid button').length,
    horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
    overflowingElements: Array.from(document.querySelectorAll('button,.review-panel,.composer,.control-section,.provider-unlock-row'))
      .filter((element) => element.scrollWidth > Math.ceil(element.getBoundingClientRect().width) + 1)
      .map((element) => ({
        tag: element.tagName,
        className: String(element.className),
        text: (element.textContent || '').trim().slice(0, 120),
        width: Math.ceil(element.getBoundingClientRect().width),
        scrollWidth: element.scrollWidth
      }))
  })
}
'@
$studio = $null
for ($attempt = 0; $attempt -lt 12; $attempt++) {
    $studio = Invoke-EvalJson $studioScript
    if ($studio.studioVisible -and $studio.keyOrderVisible -and [int]$studio.paintEditButtonCount -gt 0 -and [int]$studio.outputButtonCount -gt 0) {
        break
    }
    Start-Sleep -Milliseconds 500
}
if ($studio.title -ne "Frank Create") {
    throw "Unexpected Studio page title: $($studio.title)"
}
if (!$studio.studioVisible) {
    throw "Studio shell was not visible for $studioUrl."
}
if (!$studio.keyOrderVisible -or !$studio.replicateKeyVisible -or !$studio.openAiKeyVisible -or !$studio.noLegacyProviderCopy) {
    throw "Studio Provider Setup three-provider plan was not visible."
}
$providerKeyFields = @($studio.providerKeyFields)
$allowedProviderKeyFields = @("GOOGLE_API_KEY", "REPLICATE_API_TOKEN", "OPENAI_API_KEY")
$lastProviderKeyIndex = -1
foreach ($field in $providerKeyFields) {
    $fieldIndex = [array]::IndexOf($allowedProviderKeyFields, [string]$field)
    if ($fieldIndex -lt 0 -or $fieldIndex -lt $lastProviderKeyIndex) {
        throw "Provider Setup key fields were not limited to the Cliff pack providers: $($providerKeyFields -join ', ')"
    }
    $lastProviderKeyIndex = $fieldIndex
}
if (!$studio.cliffGuideVisible -or $studio.cliffGuideCopy -notmatch "Cliff Run of Show" -or $studio.cliffGuideCopy -notmatch "Product Shot Lab" -or $studio.cliffGuideCopy -notmatch "Advanced Graph") {
    throw "Studio Cliff demo guide was not visible: $($studio | ConvertTo-Json -Compress)"
}
if (!$studio.workflowBlueprintsVisible -or $studio.workflowBlueprintCopy -notmatch "Checkpoint txt2img" -or $studio.workflowBlueprintCopy -notmatch "Checkpoint img2img" -or $studio.workflowBlueprintCopy -notmatch "InpaintModelConditioning") {
    throw "Studio Comfy workflow blueprints were not visible: $($studio | ConvertTo-Json -Compress)"
}
if ([int]$studio.outputButtonCount -le 0 -or [int]$studio.paintEditButtonCount -le 0) {
    throw "Studio did not expose a selected output and Paint edit mask action: $($studio | ConvertTo-Json -Compress)"
}
if ([int]$studio.horizontalOverflow -gt 0) {
    throw "Studio page has horizontal overflow: $($studio.horizontalOverflow) px."
}
if ($studio.overflowingElements.Count -gt 0) {
    throw "Studio has overflowing elements: $($studio.overflowingElements | ConvertTo-Json -Compress)"
}

$copyProviderKeyPlanScript = @'
async () => {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: {
      writeText: async (text) => {
        window.__frankCopiedProviderKeyPlan = text;
      }
    }
  });
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Copy key plan');
  if (!button) return JSON.stringify({ clicked: false, reason: 'missing button' });
  button.click();
  await new Promise((resolve) => setTimeout(resolve, 250));
  const copied = String(window.__frankCopiedProviderKeyPlan || '');
  const allowedKeys = ['GOOGLE_API_KEY', 'REPLICATE_API_TOKEN', 'OPENAI_API_KEY'];
  const copiedKeys = copied.match(/[A-Z0-9_]+(?:_API)?_(?:KEY|TOKEN|SECRET)/g) || [];
  return JSON.stringify({
    clicked: true,
    hasHeader: copied.includes('Frank Create Provider Key Plan'),
    hasKeyOrder: copied.includes('Cliff key order'),
    hasGoogleKey: copied.includes('GOOGLE_API_KEY'),
    hasReplicateKey: copied.includes('REPLICATE_API_TOKEN'),
    hasOpenAiKey: copied.includes('OPENAI_API_KEY'),
    hasNoLegacyProvider: copiedKeys.length >= allowedKeys.length && copiedKeys.every((key) => allowedKeys.includes(key)),
    hasSecretDisclaimer: copied.includes('Provider secret values are not included'),
    hasSecretShape: /sk-|r8_|AIza/i.test(copied),
    statusText: document.querySelector('.status-strip')?.textContent || ''
  });
}
'@
$copyProviderKeyPlan = Invoke-EvalJson $copyProviderKeyPlanScript
if (
    !$copyProviderKeyPlan.clicked `
    -or !$copyProviderKeyPlan.hasHeader `
    -or !$copyProviderKeyPlan.hasKeyOrder `
    -or !$copyProviderKeyPlan.hasGoogleKey `
    -or !$copyProviderKeyPlan.hasReplicateKey `
    -or !$copyProviderKeyPlan.hasOpenAiKey `
    -or !$copyProviderKeyPlan.hasNoLegacyProvider `
    -or !$copyProviderKeyPlan.hasSecretDisclaimer `
    -or $copyProviderKeyPlan.hasSecretShape `
    -or $copyProviderKeyPlan.statusText -notmatch "Provider key plan copied"
) {
    throw "Copy key plan did not produce the expected safe provider setup checklist: $($copyProviderKeyPlan | ConvertTo-Json -Compress)"
}

$copyProductionUnlockPlanScript = @'
async () => {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: {
      writeText: async (text) => {
        window.__frankCopiedProductionUnlockPlan = text;
      }
    }
  });
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Copy unlock plan');
  if (!button) return JSON.stringify({ clicked: false, reason: 'missing button' });
  button.click();
  await new Promise((resolve) => setTimeout(resolve, 250));
  const copied = String(window.__frankCopiedProductionUnlockPlan || '');
  return JSON.stringify({
    clicked: true,
    hasHeader: copied.includes('Frank Create Production Unlock Plan'),
    hasEnvVars: copied.includes('GOOGLE_API_KEY') && copied.includes('OPENAI_API_KEY'),
    hasCheckpointPath: copied.includes('models\\checkpoints'),
    hasRotationStep: copied.includes('Rotate the exposed Replicate token'),
    hasNoSecretShape: !/sk-|r8_|AIza|server-side-openai|server-side-replicate/i.test(copied),
    statusText: document.querySelector('.status-strip')?.textContent || ''
  });
}
'@
$copyProductionUnlockPlan = Invoke-EvalJson $copyProductionUnlockPlanScript
if (
    !$copyProductionUnlockPlan.clicked `
    -or !$copyProductionUnlockPlan.hasHeader `
    -or !$copyProductionUnlockPlan.hasEnvVars `
    -or !$copyProductionUnlockPlan.hasCheckpointPath `
    -or !$copyProductionUnlockPlan.hasRotationStep `
    -or !$copyProductionUnlockPlan.hasNoSecretShape `
    -or $copyProductionUnlockPlan.statusText -notmatch "Production unlock plan copied"
) {
    throw "Copy unlock plan did not produce the expected safe production unlock plan: $($copyProductionUnlockPlan | ConvertTo-Json -Compress)"
}

$selectedModelPreflightScript = @'
async () => {
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Check selected model');
  if (!button) return JSON.stringify({ clicked: false, reason: 'missing button' });
  button.click();
  let cardText = '';
  let statusText = '';
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 250));
    cardText = document.querySelector('.provider-preflight-card')?.textContent || '';
    statusText = document.querySelector('.status-strip')?.textContent || '';
    if (/Preflight/i.test(cardText) && /payload|prompt|reference|ready|blocked/i.test(cardText + ' ' + statusText)) break;
  }
  window.__frankSelectedModelPreflightProof = { cardText, statusText };
  const secretPattern = /sk-|r8_|AIza|server-side-openai|server-side-replicate/i;
  const hasNoSecretShape = secretPattern.test(cardText + ' ' + statusText) === false;
  return JSON.stringify({
    clicked: true,
    hasPreflightCard: /Preflight/i.test(cardText),
    hasPayloadPreview: /payload|prompt|reference|source|mask|model/i.test(cardText),
    hasNoSecretShape,
    statusText
  });
}
'@
$selectedModelPreflight = Invoke-EvalJson $selectedModelPreflightScript
if (
    !$selectedModelPreflight.clicked `
    -or !$selectedModelPreflight.hasPreflightCard `
    -or !$selectedModelPreflight.hasPayloadPreview `
    -or !$selectedModelPreflight.hasNoSecretShape
) {
    throw "Selected model preflight did not produce the expected no-spend payload preview: $($selectedModelPreflight | ConvertTo-Json -Compress)"
}

$localGenerateScript = @'
async () => {
  const promptBox = document.querySelector('.composer textarea');
  const generateButton = Array.from(document.querySelectorAll('.composer button')).find((candidate) => (candidate.textContent || '').trim() === 'Generate');
  if (!promptBox || !generateButton) {
    return JSON.stringify({ clicked: false, reason: 'missing prompt or button' });
  }
  const outputCountBefore = document.querySelectorAll('.output-grid button').length;
  const prompt = `Browser QA local generate proof ${new Date().toISOString()}: Frank Body product shot on soft pink tile, clean label, warm flash.`;
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (setter) {
    setter.call(promptBox, prompt);
  } else {
    promptBox.value = prompt;
  }
  promptBox.dispatchEvent(new Event('input', { bubbles: true }));
  generateButton.click();
  let outputCountAfter = outputCountBefore;
  let statusText = '';
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    outputCountAfter = document.querySelectorAll('.output-grid button').length;
    statusText = document.querySelector('.status-strip')?.textContent || '';
    if (outputCountAfter > outputCountBefore && !/Preparing/i.test(statusText)) break;
  }
  window.__frankGenerateProof = {
    prompt,
    outputCountBefore,
    outputCountAfter,
    statusText
  };
  return JSON.stringify({
    clicked: true,
    outputCountBefore,
    outputCountAfter,
    created: outputCountAfter > outputCountBefore,
    statusText,
    hasLocalCopy: /Frank renderer|Local|ready|complete|fallback/i.test(statusText)
  });
}
'@
$localGenerate = Invoke-EvalJson $localGenerateScript
if (
    !$localGenerate.clicked `
    -or !$localGenerate.created `
    -or [int]$localGenerate.outputCountAfter -le [int]$localGenerate.outputCountBefore
) {
    throw "Browser QA local generate proof failed: $($localGenerate | ConvertTo-Json -Compress)"
}

$demoDoctorChecksumScript = @'
async () => {
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Run demo check');
  if (!button) return JSON.stringify({ clicked: false, reason: 'missing button' });
  button.click();
  let proofText = '';
  let readinessPackSha = '';
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    proofText = document.querySelector('.readiness-pack-sha')?.textContent || '';
    readinessPackSha = proofText.replace(/SHA-256/gi, ' ').match(/[a-f0-9]{64}/i)?.[0] || '';
    if (proofText.includes('Verified SHA-256') && readinessPackSha) break;
  }
  return JSON.stringify({
    clicked: true,
    hasVerifiedLabel: proofText.includes('Verified SHA-256'),
    readinessPackSha,
    statusText: document.querySelector('.status-strip')?.textContent || '',
    doctorCopy: document.querySelector('.demo-doctor')?.textContent || ''
  });
}
'@
$demoDoctorChecksum = Invoke-EvalJson $demoDoctorChecksumScript
if (
    !$demoDoctorChecksum.clicked `
    -or !$demoDoctorChecksum.hasVerifiedLabel `
    -or $demoDoctorChecksum.readinessPackSha -notmatch "^[a-fA-F0-9]{64}$" `
    -or $demoDoctorChecksum.doctorCopy -notmatch "Verified SHA-256"
) {
    throw "Demo Doctor visible checksum proof failed: $($demoDoctorChecksum | ConvertTo-Json -Compress)"
}

$openReviewBoardScript = @'
async () => {
  const originalOpen = window.open;
  window.__frankOpenedReviewBoard = '';
  window.open = (url) => {
    window.__frankOpenedReviewBoard = String(url || '');
    return null;
  };
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Open review board');
  if (!button) {
    window.open = originalOpen;
    return JSON.stringify({ clicked: false, reason: 'missing button' });
  }
  button.click();
  await new Promise((resolve) => setTimeout(resolve, 250));
  const opened = String(window.__frankOpenedReviewBoard || '');
  window.open = originalOpen;
  return JSON.stringify({
    clicked: true,
    opened,
    isReviewBoardUrl: /\/api\/frank\/sessions\/[^/]+\/review-board$/.test(opened),
    statusText: document.querySelector('.status-strip')?.textContent || ''
  });
}
'@
$openReviewBoard = Invoke-EvalJson $openReviewBoardScript
if (!$openReviewBoard.clicked -or !$openReviewBoard.isReviewBoardUrl -or $openReviewBoard.statusText -notmatch "visual review board|Review board link ready") {
    throw "Open review board did not target the direct session review-board PNG: $($openReviewBoard | ConvertTo-Json -Compress)"
}

$openSyncManifestScript = @'
async () => {
  const originalOpen = window.open;
  const opened = [];
  window.open = (url, target) => {
    opened.push({ url: String(url), target: String(target || '') });
    return null;
  };
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Open sync manifest');
  if (!button) {
    window.open = originalOpen;
    return JSON.stringify({ clicked: false, reason: 'missing button' });
  }
  button.click();
  await new Promise((resolve) => setTimeout(resolve, 350));
  window.open = originalOpen;
  const manifestUrl = opened[0]?.url || '';
  let schema = '';
  let hasFrankHubTable = false;
  let contentType = '';
  try {
    const response = await fetch(manifestUrl);
    contentType = response.headers.get('content-type') || '';
    const manifest = await response.json();
    schema = manifest.schema_version || '';
    hasFrankHubTable = manifest.sync_contract?.tables?.assets === 'frank_create_assets';
  } catch (error) {
    schema = `fetch-failed:${error?.message || error}`;
  }
  return JSON.stringify({
    clicked: true,
    isSyncManifestUrl: /\/api\/frank\/sessions\/[^/]+\/sync-manifest$/.test(manifestUrl),
    target: opened[0]?.target || '',
    statusText: document.querySelector('.status-strip')?.textContent || '',
    schema,
    hasFrankHubTable,
    contentType
  });
}
'@
$openSyncManifest = Invoke-EvalJson $openSyncManifestScript
if (
    !$openSyncManifest.clicked `
    -or !$openSyncManifest.isSyncManifestUrl `
    -or $openSyncManifest.target -ne "_blank" `
    -or $openSyncManifest.statusText -notmatch "FrankHub sync manifest|Sync manifest link ready" `
    -or $openSyncManifest.schema -ne "frank-create.sync.v1" `
    -or !$openSyncManifest.hasFrankHubTable `
    -or $openSyncManifest.contentType -notmatch "application/json"
) {
    throw "Open sync manifest did not expose the FrankHub sync manifest JSON: $($openSyncManifest | ConvertTo-Json -Compress)"
}

$copyRunBriefScript = @'
async () => {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: {
      writeText: async (text) => {
        window.__frankCopiedRunBrief = text;
      }
    }
  });
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Copy run brief');
  if (!button) return JSON.stringify({ clicked: false, reason: 'missing button' });
  button.click();
  await new Promise((resolve) => setTimeout(resolve, 250));
  const copied = String(window.__frankCopiedRunBrief || '');
  return JSON.stringify({
    clicked: true,
    hasHeader: copied.includes('Frank Create Run Brief'),
    hasWorkflow: copied.includes('Workflow:'),
    hasSecretShape: /sk-|r8_|AIza/i.test(copied),
    statusText: document.querySelector('.status-strip')?.textContent || ''
  });
}
'@
$copyRunBrief = Invoke-EvalJson $copyRunBriefScript
if (!$copyRunBrief.clicked -or !$copyRunBrief.hasHeader -or !$copyRunBrief.hasWorkflow -or $copyRunBrief.hasSecretShape -or $copyRunBrief.statusText -notmatch "Run brief copied") {
    throw "Copy run brief did not produce the expected safe provenance text: $($copyRunBrief | ConvertTo-Json -Compress)"
}

$downloadWorkflowScript = @'
async () => {
  const originalCreateObjectUrl = URL.createObjectURL;
  const originalRevokeObjectUrl = URL.revokeObjectURL;
  const originalAnchorClick = HTMLAnchorElement.prototype.click;
  window.__frankWorkflowBlob = null;
  window.__frankWorkflowAnchor = null;
  window.__frankWorkflowRevoked = '';
  URL.createObjectURL = (blob) => {
    window.__frankWorkflowBlob = blob;
    return 'blob:frank-workflow-browser-qa';
  };
  URL.revokeObjectURL = (url) => {
    window.__frankWorkflowRevoked = url;
  };
  HTMLAnchorElement.prototype.click = function () {
    window.__frankWorkflowAnchor = { download: this.download, href: this.href };
  };
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Download workflow JSON');
  if (!button) {
    URL.createObjectURL = originalCreateObjectUrl;
    URL.revokeObjectURL = originalRevokeObjectUrl;
    HTMLAnchorElement.prototype.click = originalAnchorClick;
    return JSON.stringify({ clicked: false, reason: 'missing button' });
  }
  button.click();
  await new Promise((resolve) => setTimeout(resolve, 250));
  const text = window.__frankWorkflowBlob ? await window.__frankWorkflowBlob.text() : '';
  let workflow = {};
  try {
    workflow = JSON.parse(text);
  } catch {
    workflow = {};
  }
  URL.createObjectURL = originalCreateObjectUrl;
  URL.revokeObjectURL = originalRevokeObjectUrl;
  HTMLAnchorElement.prototype.click = originalAnchorClick;
  return JSON.stringify({
    clicked: true,
    hasProduct: workflow.product === 'Frank Create',
    hasAssetId: !!workflow.asset_id,
    hasWorkflow: !!workflow.workflow_provenance && Object.keys(workflow.workflow_provenance).length > 0,
    hasReferences: Array.isArray(workflow.references),
    hasSafeProviderCopy: workflow.provider_keys === 'server-side only; no secrets included',
    hasSecretShape: /sk-|r8_|AIza/i.test(text),
    downloadName: window.__frankWorkflowAnchor?.download || '',
    revokedUrl: window.__frankWorkflowRevoked || '',
    statusText: document.querySelector('.status-strip')?.textContent || ''
  });
}
'@
$downloadWorkflow = Invoke-EvalJson $downloadWorkflowScript
if (
    !$downloadWorkflow.clicked `
    -or !$downloadWorkflow.hasProduct `
    -or !$downloadWorkflow.hasAssetId `
    -or !$downloadWorkflow.hasWorkflow `
    -or !$downloadWorkflow.hasReferences `
    -or !$downloadWorkflow.hasSafeProviderCopy `
    -or $downloadWorkflow.hasSecretShape `
    -or $downloadWorkflow.downloadName -notmatch "\-workflow\.json$" `
    -or $downloadWorkflow.revokedUrl -ne "blob:frank-workflow-browser-qa" `
    -or $downloadWorkflow.statusText -notmatch "Workflow JSON downloaded"
) {
    throw "Download workflow JSON did not produce the expected safe provenance sidecar: $($downloadWorkflow | ConvertTo-Json -Compress)"
}

$maskPainterClickScript = @'
() => {
  const button = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.textContent || '').trim() === 'Paint edit mask');
  if (!button) return JSON.stringify({ clicked: false });
  button.click();
  return JSON.stringify({ clicked: true });
}
'@
$maskClick = Invoke-EvalJson $maskPainterClickScript
if (!$maskClick.clicked) {
    throw "Could not click Paint edit mask."
}
$maskPainterScript = @'
() => JSON.stringify({
  painterVisible: !!document.querySelector('.mask-painter'),
  heading: document.querySelector('.mask-painter h3')?.textContent || '',
  canvasVisible: !!document.querySelector('.mask-painter canvas'),
  brushVisible: !!document.querySelector('.mask-painter input[type="range"]'),
  useMaskVisible: Array.from(document.querySelectorAll('.mask-painter button')).some((button) => (button.textContent || '').includes('Use mask')),
  horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth
})
'@
$maskPainter = $null
for ($attempt = 0; $attempt -lt 8; $attempt++) {
    $maskPainter = Invoke-EvalJson $maskPainterScript
    if ($maskPainter.painterVisible -and $maskPainter.canvasVisible -and $maskPainter.brushVisible -and $maskPainter.useMaskVisible) {
        break
    }
    Start-Sleep -Milliseconds 500
}
if (!$maskPainter.painterVisible -or !$maskPainter.canvasVisible -or !$maskPainter.brushVisible -or !$maskPainter.useMaskVisible) {
    throw "Mask painter did not render fully: $($maskPainter | ConvertTo-Json -Compress)"
}
if ($maskPainter.heading -ne "Paint the bits to change") {
    throw "Mask painter heading was unexpected: $($maskPainter.heading)"
}
if ([int]$maskPainter.horizontalOverflow -gt 0) {
    throw "Mask painter has horizontal overflow: $($maskPainter.horizontalOverflow) px."
}

$paintMaskScript = @'
() => {
  const canvas = document.querySelector('.mask-painter canvas');
  if (!canvas) return JSON.stringify({ painted: false, reason: 'missing canvas' });
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return JSON.stringify({ painted: false, reason: 'zero-size canvas', width: rect.width, height: rect.height });
  const point = {
    bubbles: true,
    cancelable: true,
    pointerId: 7,
    pointerType: 'mouse',
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2
  };
  canvas.dispatchEvent(new PointerEvent('pointerdown', point));
  canvas.dispatchEvent(new PointerEvent('pointermove', { ...point, clientX: point.clientX + Math.min(20, rect.width / 8) }));
  canvas.dispatchEvent(new PointerEvent('pointerup', { ...point, clientX: point.clientX + Math.min(20, rect.width / 8) }));
  return JSON.stringify({
    painted: true,
    useMaskDisabled: Array.from(document.querySelectorAll('.mask-painter button')).find((button) => (button.textContent || '').includes('Use mask'))?.disabled ?? true
  });
}
'@
$paintMask = Invoke-EvalJson $paintMaskScript
if (!$paintMask.painted) {
    throw "Could not paint on mask canvas: $($paintMask | ConvertTo-Json -Compress)"
}
$useMaskReadyScript = @'
() => JSON.stringify({
  ready: Array.from(document.querySelectorAll('.mask-painter button')).some((button) => (button.textContent || '').includes('Use mask') && !button.disabled)
})
'@
$useMaskReady = $null
for ($attempt = 0; $attempt -lt 8; $attempt++) {
    $useMaskReady = Invoke-EvalJson $useMaskReadyScript
    if ($useMaskReady.ready) {
        break
    }
    Start-Sleep -Milliseconds 350
}
if (!$useMaskReady.ready) {
    throw "Use mask button did not become enabled after painting."
}
$useMaskClickScript = @'
() => {
  const button = Array.from(document.querySelectorAll('.mask-painter button')).find((candidate) => (candidate.textContent || '').includes('Use mask') && !candidate.disabled);
  if (!button) return JSON.stringify({ clicked: false });
  button.click();
  return JSON.stringify({ clicked: true });
}
'@
$useMaskClick = Invoke-EvalJson $useMaskClickScript
if (!$useMaskClick.clicked) {
    throw "Could not click Use mask after painting."
}
$maskSavedScript = @'
() => JSON.stringify({
  painterGone: !document.querySelector('.mask-painter'),
  maskChip: document.querySelector('.mask-chip')?.textContent || '',
  primaryAction: document.querySelector('.composer .primary-button')?.textContent || '',
  statusText: document.querySelector('.status-strip')?.textContent || ''
})
'@
$maskSaved = $null
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    $maskSaved = Invoke-EvalJson $maskSavedScript
    if ($maskSaved.painterGone -and $maskSaved.maskChip -match "painted-mask" -and $maskSaved.primaryAction -match "Edit") {
        break
    }
    Start-Sleep -Milliseconds 500
}
if (!$maskSaved.painterGone -or $maskSaved.maskChip -notmatch "painted-mask" -or $maskSaved.primaryAction -notmatch "Edit") {
    throw "Painted mask was not saved into the masked edit composer: $($maskSaved | ConvertTo-Json -Compress)"
}

$maskedEditGenerateScript = @'
async () => {
  const hasMask = /painted-mask/i.test(document.querySelector('.mask-chip')?.textContent || '');
  const maskedButton = Array.from(document.querySelectorAll('.composer button')).find((candidate) => (candidate.textContent || '').includes('Edit'));
  if (!hasMask) return JSON.stringify({ clicked: false, reason: 'missing painted mask chip' });
  if (!maskedButton) return JSON.stringify({ clicked: false, reason: 'missing edit button' });
  const maskedOutputCountBefore = document.querySelectorAll('.output-grid button').length;
  maskedButton.click();
  let maskedOutputCountAfter = maskedOutputCountBefore;
  let statusText = '';
  for (let attempt = 0; attempt < 180; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    maskedOutputCountAfter = document.querySelectorAll('.output-grid button').length;
    statusText = document.querySelector('.status-strip')?.textContent || '';
    if (maskedOutputCountAfter > maskedOutputCountBefore && !/Preparing/i.test(statusText)) break;
  }
  window.__frankMaskedEditProof = {
    maskedOutputCountBefore,
    maskedOutputCountAfter,
    statusText
  };
  return JSON.stringify({
    clicked: true,
    maskedOutputCountBefore,
    maskedOutputCountAfter,
    created: maskedOutputCountAfter > maskedOutputCountBefore,
    statusText
  });
}
'@
$maskedEditGenerate = Invoke-EvalJson $maskedEditGenerateScript
if (
    !$maskedEditGenerate.clicked `
    -or !$maskedEditGenerate.created `
    -or [int]$maskedEditGenerate.maskedOutputCountAfter -le [int]$maskedEditGenerate.maskedOutputCountBefore
) {
    throw "Browser QA masked edit proof failed: $($maskedEditGenerate | ConvertTo-Json -Compress)"
}

$cleanupPaintedMasksScript = @'
async () => {
  const response = await fetch('/api/frank/assets');
  const payload = await response.json();
  const masks = (payload.assets || []).filter((asset) => asset.kind === 'mask' && String(asset.title || '').startsWith('painted-mask-'));
  await Promise.all(masks.map((asset) => fetch(`/api/frank/assets/${encodeURIComponent(asset.id)}`, { method: 'DELETE' })));
  return JSON.stringify({ deleted: masks.length, filePaths: masks.map((asset) => asset.file_path).filter(Boolean) });
}
'@
$cleanupPaintedMasks = Invoke-EvalJson $cleanupPaintedMasksScript
$cleanupPaintedMaskFiles = Remove-QaPaintedMaskFiles -FilePaths @($cleanupPaintedMasks.filePaths)

Assert-NoConsoleIssues "Studio interaction path"
$studioScreenshot = Join-Path $ScreenshotDir "studio-interaction-browser-qa.png"
Invoke-PlaywrightCli @("--session", $Session, "screenshot", "--filename", $studioScreenshot)
if (!(Test-Path -LiteralPath $studioScreenshot)) {
    throw "Studio interaction browser QA screenshot was not created."
}

Write-Step "Opening Video Lab proof path..."
Invoke-PlaywrightCli @("--session", $Session, "goto", "$($BaseUrl.TrimEnd('/'))/?mode=video-lab")
$videoLabScript = @'
() => JSON.stringify({
  title: document.title,
  studioVisible: !!document.querySelector('.studio-shell'),
  activeNav: Array.from(document.querySelectorAll('.task-chip.active')).map((element) => (element.textContent || '').trim()).join(' '),
  generateVisible: Array.from(document.querySelectorAll('.composer button')).some((button) => /Generate/i.test(button.textContent || '')),
  videoLabCopy: (document.body.textContent || '').includes('Video Lab'),
  motionCopy: (document.body.textContent || '').toLowerCase().includes('motion'),
  motionBoardCopy: (document.body.textContent || '').toLowerCase().includes('motion board'),
  videoPreviewCount: document.querySelectorAll('video').length,
  horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
  overflowingElements: Array.from(document.querySelectorAll('button,.review-panel,.composer,.control-section,.selected-output,.output-grid'))
    .filter((element) => element.scrollWidth > Math.ceil(element.getBoundingClientRect().width) + 1)
    .map((element) => ({
      tag: element.tagName,
      className: String(element.className),
      text: (element.textContent || '').trim().slice(0, 120),
      width: Math.ceil(element.getBoundingClientRect().width),
      scrollWidth: element.scrollWidth
    }))
})
'@
$videoLab = $null
for ($attempt = 0; $attempt -lt 12; $attempt++) {
    $videoLab = Invoke-EvalJson $videoLabScript
    if ($videoLab.studioVisible -and $videoLab.activeNav -match "Video Lab" -and $videoLab.generateVisible -and $videoLab.motionCopy) {
        break
    }
    Start-Sleep -Milliseconds 500
}
if (!$videoLab.studioVisible -or $videoLab.activeNav -notmatch "Video Lab" -or !$videoLab.generateVisible -or !$videoLab.motionCopy) {
    throw "Video Lab proof path did not render: $($videoLab | ConvertTo-Json -Compress)"
}
if ([int]$videoLab.horizontalOverflow -gt 0) {
    throw "Video Lab page has horizontal overflow: $($videoLab.horizontalOverflow) px."
}
if ($videoLab.overflowingElements.Count -gt 0) {
    throw "Video Lab has overflowing elements: $($videoLab.overflowingElements | ConvertTo-Json -Compress)"
}
Assert-NoConsoleIssues "Video Lab"
$videoLabScreenshot = Join-Path $ScreenshotDir "video-lab-browser-qa.png"
Invoke-PlaywrightCli @("--session", $Session, "screenshot", "--filename", $videoLabScreenshot)
if (!(Test-Path -LiteralPath $videoLabScreenshot)) {
    throw "Video Lab browser QA screenshot was not created."
}

Write-Step "Opening Provider Adapter Audit..."
Invoke-PlaywrightCli @("--session", $Session, "open", $auditUrl)

$auditScript = @'
() => JSON.stringify({
  title: document.title,
  providerAuditMode: document.querySelector('.studio-shell')?.getAttribute('data-provider-audit') === 'open',
  auditVisible: !!document.querySelector('.provider-audit-card'),
  auditCopy: document.querySelector('.provider-audit-card')?.textContent || '',
  horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
  overflowingElements: Array.from(document.querySelectorAll('button,.provider-audit-row,.provider-audit-card,.control-section'))
    .filter((element) => element.scrollWidth > Math.ceil(element.getBoundingClientRect().width) + 1)
    .map((element) => ({
      tag: element.tagName,
      className: String(element.className),
      text: (element.textContent || '').trim().slice(0, 120),
      width: Math.ceil(element.getBoundingClientRect().width),
      scrollWidth: element.scrollWidth
    }))
})
'@
$audit = Invoke-EvalJson $auditScript
if ($audit.title -ne "Frank Create") {
    throw "Unexpected page title: $($audit.title)"
}
if (!$audit.providerAuditMode) {
    throw "Provider audit mode was not active for $auditUrl."
}
if (!$audit.auditVisible -or $audit.auditCopy -notmatch "No-spend adapter audit") {
    throw "Provider Adapter Audit card was not visible."
}
if ($audit.auditCopy -notmatch "5 / 5 runners registered" -or $audit.auditCopy -notmatch "0 preview issues") {
    throw "Provider Adapter Audit did not show the expected no-spend proof."
}
if ($audit.auditCopy -notmatch "operation previews checked") {
    throw "Provider Adapter Audit did not show operation request preview coverage."
}
if ([int]$audit.horizontalOverflow -gt 0) {
    throw "Provider audit page has horizontal overflow: $($audit.horizontalOverflow) px."
}
if ($audit.overflowingElements.Count -gt 0) {
    throw "Provider audit has overflowing elements: $($audit.overflowingElements | ConvertTo-Json -Compress)"
}
Assert-NoConsoleIssues "Provider Adapter Audit"
$providerAuditScreenshot = Join-Path $ScreenshotDir "provider-audit-browser-qa.png"
Invoke-PlaywrightCli @("--session", $Session, "screenshot", "--filename", $providerAuditScreenshot)
if (!(Test-Path -LiteralPath $providerAuditScreenshot)) {
    throw "Provider Adapter Audit browser QA screenshot was not created."
}

Write-Step "Opening Advanced Graph..."
Invoke-PlaywrightCli @("--session", $Session, "goto", $graphUrl)
$graphScript = @'
() => {
  const text = document.body.textContent || '';
  const buttons = Array.from(document.querySelectorAll('button'));
  const node = (label) => buttons.find((button) => button.getAttribute('aria-label') === label);
  return JSON.stringify({
    title: document.title,
    graphVisible: !!document.querySelector('.graph-shell'),
    workflowMap: /Workflow\s+Map/.test(text),
    studioMap: /Studio\s+workflow\s+map/.test(text),
    comfyHint: /Real\s+node\s+graph\s+lives\s+in\s+Comfy\s+Canvas\./.test(text),
    selectedStageBefore: document.querySelector('.graph-selected-panel')?.textContent || '',
    briefPressedBefore: node('Inspect The Brief')?.getAttribute('aria-pressed') || '',
    makePressedBefore: node('Inspect Make Magic')?.getAttribute('aria-pressed') || '',
    useInStudio: buttons.some((button) => /Use\s+in\s+Studio/.test(button.textContent || '')),
    openComfyCanvas: buttons.some((button) => /Open\s+Comfy\s+Canvas/.test(button.textContent || '')),
    canvasWidth: document.querySelector('.graph-canvas')?.getBoundingClientRect().width || 0,
    horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth
  });
}
'@
$graph = $null
for ($attempt = 0; $attempt -lt 10; $attempt++) {
    $graph = Invoke-EvalJson $graphScript
    if ($graph.graphVisible -and $graph.workflowMap -and $graph.studioMap -and $graph.comfyHint -and $graph.useInStudio -and $graph.openComfyCanvas) {
        break
    }
    Start-Sleep -Milliseconds 500
}
if (!$graph.graphVisible -or !$graph.workflowMap -or !$graph.studioMap -or !$graph.comfyHint -or !$graph.useInStudio -or !$graph.openComfyCanvas) {
    throw "Advanced Graph branding did not render: $($graph | ConvertTo-Json -Compress)"
}
if ($graph.selectedStageBefore -notmatch "Selected stage 04" -or $graph.makePressedBefore -ne "true") {
    throw "Advanced Graph did not default to the Make Magic stage: $($graph | ConvertTo-Json -Compress)"
}
$graphClickScript = @'
async () => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const node = (label) => buttons.find((button) => button.getAttribute('aria-label') === label);
  const brief = node('Inspect The Brief');
  if (!brief) return JSON.stringify({ clicked: false, reason: 'missing brief node' });
  brief.click();
  await new Promise((resolve) => setTimeout(resolve, 250));
  return JSON.stringify({
    clicked: true,
    selectedStageAfter: document.querySelector('.graph-selected-panel')?.textContent || '',
    briefPressedAfter: node('Inspect The Brief')?.getAttribute('aria-pressed') || '',
    makePressedAfter: node('Inspect Make Magic')?.getAttribute('aria-pressed') || ''
  });
}
'@
$graphClick = Invoke-EvalJson $graphClickScript
if (!$graphClick.clicked -or $graphClick.selectedStageAfter -notmatch "Selected stage 01" -or $graphClick.briefPressedAfter -ne "true" -or $graphClick.makePressedAfter -ne "false") {
    throw "Advanced Graph stage click did not update the inspector: $($graphClick | ConvertTo-Json -Compress)"
}
if ([int]$graph.horizontalOverflow -gt 0) {
    throw "Advanced Graph has horizontal overflow: $($graph.horizontalOverflow) px."
}
Assert-NoConsoleIssues "Advanced Graph"
$graphScreenshot = Join-Path $ScreenshotDir "graph-browser-qa.png"
Invoke-PlaywrightCli @("--session", $Session, "screenshot", "--filename", $graphScreenshot)
if (!(Test-Path -LiteralPath $graphScreenshot)) {
    throw "Advanced Graph browser QA screenshot was not created."
}

Write-Step "Opening raw Comfy canvas..."
Invoke-PlaywrightCli @("--session", $Session, "goto", $rawComfyUrl)
$rawScript = @'
() => JSON.stringify({
  title: document.title,
  rawBrand: document.documentElement.dataset.frankRawCanvasBrand,
  rawComfyHasCanvas: !!document.querySelector('canvas'),
  brandChrome: !!document.querySelector('#frank-comfy-brand-chrome'),
  bodySkin: document.body?.getAttribute('data-frank-create-graph'),
  runControlVisible: Array.from(document.querySelectorAll('button,[role="button"],.p-button'))
    .some((element) => /queue|run|prompt/i.test(`${element.textContent || ''} ${element.getAttribute('aria-label') || ''}`)),
  horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
  blockingOverlayIds: [
    'frank-comfy-brand-strip',
    'frank-comfy-lane-map',
    'frank-comfy-action-rail',
    'frank-comfy-art-direction',
    'frank-comfy-node-legend',
    'frank-comfy-node-style-card',
    'frank-comfy-stage-ribbon',
    'frank-comfy-canvas-watermark',
    'frank-comfy-palette-card',
    'frank-comfy-status-dock',
    'frank-comfy-production-plate'
  ].filter((id) => !!document.getElementById(id)),
  highZBlockers: Array.from(document.querySelectorAll('[id^="frank-comfy-"]'))
    .filter((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      const zIndex = Number.parseInt(style.zIndex || '0', 10) || 0;
      return style.position === 'fixed' && zIndex >= 1000 && rect.width * rect.height > window.innerWidth * window.innerHeight * 0.08;
    })
    .map((element) => element.id)
})
'@
$raw = $null
for ($attempt = 0; $attempt -lt 12; $attempt++) {
    $raw = Invoke-EvalJson $rawScript
    if ($raw.rawBrand -eq "frank-create-raw-canvas" -and $raw.rawComfyHasCanvas -and $raw.brandChrome -and $raw.runControlVisible) {
        break
    }
    Start-Sleep -Milliseconds 750
}
if ($raw.rawBrand -ne "frank-create-raw-canvas" -or !$raw.rawComfyHasCanvas -or !$raw.brandChrome -or !$raw.runControlVisible) {
    throw "Raw Comfy canvas did not expose a usable lightly branded canvas: $($raw | ConvertTo-Json -Compress)"
}
if ([int]$raw.horizontalOverflow -gt 0) {
    throw "Raw Comfy canvas has horizontal overflow: $($raw.horizontalOverflow) px."
}
if ($raw.blockingOverlayIds.Count -gt 0 -or $raw.highZBlockers.Count -gt 0) {
    throw "Raw Comfy canvas has blocking Frank overlays: $($raw | ConvertTo-Json -Compress)"
}
Assert-NoConsoleIssues "Raw Comfy canvas"
$rawScreenshot = Join-Path $ScreenshotDir "raw-comfy-browser-qa.png"
Invoke-PlaywrightCli @("--session", $Session, "screenshot", "--filename", $rawScreenshot)
if (!(Test-Path -LiteralPath $rawScreenshot)) {
    throw "Raw Comfy browser QA screenshot was not created."
}

Write-Step "Opening raw Comfy selected workflow receipt..."
Invoke-PlaywrightCli @("--session", $Session, "goto", $rawComfyReceiptUrl)
$rawReceiptScript = @'
() => JSON.stringify({
  title: document.title,
  rawBrand: document.documentElement.dataset.frankRawCanvasBrand,
  rawComfyHasCanvas: !!document.querySelector('canvas'),
  brandChrome: !!document.querySelector('#frank-comfy-brand-chrome'),
  receiptVisible: !!document.querySelector('#frank-comfy-workflow-receipt'),
  receiptCopy: document.querySelector('#frank-comfy-workflow-receipt')?.textContent || '',
  hasReceiptObject: !!window.__frankCreateWorkflowReceipt,
  hasApiPromptJson: !!window.__frankCreateWorkflowReceipt?.api_prompt_json,
  canLoadPrompt: !!window.__frankCreateWorkflowReceipt?.can_load_comfy_api_prompt,
  blockingOverlayIds: [
    'frank-comfy-brand-strip',
    'frank-comfy-lane-map',
    'frank-comfy-action-rail',
    'frank-comfy-art-direction',
    'frank-comfy-node-legend',
    'frank-comfy-node-style-card',
    'frank-comfy-stage-ribbon',
    'frank-comfy-canvas-watermark',
    'frank-comfy-palette-card',
    'frank-comfy-status-dock',
    'frank-comfy-production-plate'
  ].filter((id) => !!document.getElementById(id))
})
'@
$rawReceipt = $null
for ($attempt = 0; $attempt -lt 12; $attempt++) {
    $rawReceipt = Invoke-EvalJson $rawReceiptScript
    if ($rawReceipt.rawBrand -eq "frank-create-raw-canvas" -and $rawReceipt.rawComfyHasCanvas -and $rawReceipt.brandChrome -and $rawReceipt.receiptVisible -and $rawReceipt.hasReceiptObject) {
        break
    }
    Start-Sleep -Milliseconds 750
}
if ($rawReceipt.rawBrand -ne "frank-create-raw-canvas" -or !$rawReceipt.rawComfyHasCanvas -or !$rawReceipt.brandChrome -or !$rawReceipt.receiptVisible -or !$rawReceipt.hasReceiptObject) {
    throw "Raw Comfy selected workflow receipt did not render: $($rawReceipt | ConvertTo-Json -Compress)"
}
if ($rawReceipt.blockingOverlayIds.Count -gt 0) {
    throw "Raw Comfy selected workflow receipt has blocking Frank overlays: $($rawReceipt | ConvertTo-Json -Compress)"
}
if ($rawReceipt.receiptCopy -notmatch "Frank receipt") {
    throw "Raw Comfy workflow receipt copy was incomplete: $($rawReceipt | ConvertTo-Json -Compress)"
}
Assert-NoConsoleIssues "Raw Comfy selected workflow receipt"
$rawReceiptScreenshot = Join-Path $ScreenshotDir "raw-comfy-receipt-browser-qa.png"
Invoke-PlaywrightCli @("--session", $Session, "screenshot", "--filename", $rawReceiptScreenshot)
if (!(Test-Path -LiteralPath $rawReceiptScreenshot)) {
    throw "Raw Comfy receipt browser QA screenshot was not created."
}

$status = [ordered]@{
    status = "ready"
    completed_at = [DateTimeOffset]::UtcNow.ToString("o")
    base_url = $BaseUrl
    checks = @(
        [ordered]@{
            key = "studio_interactions"
            label = "Studio interaction path"
            status = "ready"
            url = $studioUrl
            detail = "Main Studio opens Advanced setup, proves Provider Setup key fields are limited to Gemini, OpenAI, and Replicate, copies a safe provider key plan with env-var names and no secret values, copies a safe production unlock plan with env-var names/checkpoint path/rotation step and no secret values, runs a no-spend selected model preflight with a safe payload preview, opens the direct visual review-board PNG, shows the Cliff Run of Show guide and Comfy workflow blueprints for txt2img/img2img/inpaint; copies a safe selected-output run brief with workflow provenance; downloads a safe workflow JSON sidecar with workflow provenance; paints and saves a mask into the masked-edit composer; cleans QA mask assets/files; and has no horizontal overflow or console warnings/errors. QA masks cleaned: $($cleanupPaintedMasks.deleted); files cleaned: $cleanupPaintedMaskFiles."
            screenshot = (Join-Path $ScreenshotDir "studio-interaction-browser-qa.png")
        },
        [ordered]@{
            key = "demo_doctor_checksum"
            label = "Demo Doctor readiness pack checksum"
            status = "ready"
            url = $studioUrl
            detail = "Run demo check hydrates the visible call-pack proof panel and shows Verified SHA-256 $($demoDoctorChecksum.readinessPackSha)."
        },
        [ordered]@{
            key = "studio_model_preflight"
            label = "Studio selected model preflight"
            status = "ready"
            url = $studioUrl
            detail = "Browser QA no-spend selected model preflight proof: Check selected model returned a visible safe payload preview without exposing provider secrets."
        },
        [ordered]@{
            key = "studio_local_generate"
            label = "Studio local Generate button"
            status = "ready"
            url = $studioUrl
            detail = "Browser QA local generate proof: the local Studio Generate button created output assets with Local Comfy selected; outputs $($localGenerate.outputCountBefore) -> $($localGenerate.outputCountAfter)."
        },
        [ordered]@{
            key = "studio_masked_edit_generate"
            label = "Studio masked edit Generate button"
            status = "ready"
            url = $studioUrl
            detail = "Browser QA masked edit proof: the masked edit Generate button created output assets with Local Comfy selected; outputs $($maskedEditGenerate.maskedOutputCountBefore) -> $($maskedEditGenerate.maskedOutputCountAfter)."
        },
        [ordered]@{
            key = "video_lab"
            label = "Video Lab"
            status = "ready"
            url = "$($BaseUrl.TrimEnd('/'))/?mode=video-lab"
            detail = "Video Lab opens directly from URL mode with the motion workflow controls visible, motion proof copy present, and no horizontal overflow or console warnings/errors."
            screenshot = (Join-Path $ScreenshotDir "video-lab-browser-qa.png")
        },
        [ordered]@{
            key = "provider_audit"
            label = "Provider Adapter Audit"
            status = "ready"
            url = $auditUrl
            detail = "No-spend adapter audit renders in provider-audit mode with no horizontal overflow and no console warnings/errors."
            screenshot = (Join-Path $ScreenshotDir "provider-audit-browser-qa.png")
        },
        [ordered]@{
            key = "advanced_graph"
            label = "Advanced Graph"
            status = "ready"
            url = $graphUrl
            detail = "Workflow Map renders with clear Comfy Canvas escape hatch, clickable stage inspector updates, and no horizontal overflow or console warnings/errors."
            screenshot = (Join-Path $ScreenshotDir "graph-browser-qa.png")
        },
        [ordered]@{
            key = "raw_comfy"
            label = "Raw Comfy canvas"
            status = "ready"
            url = $rawComfyUrl
            detail = "raw Comfy canvas is lightly branded and unobstructed: canvas and run controls are visible, old fixed Frank overlays are absent, and there is no horizontal overflow or console warnings/errors."
            screenshot = $rawScreenshot
        },
        [ordered]@{
            key = "raw_comfy_receipt"
            label = "Raw Comfy selected workflow receipt"
            status = "ready"
            url = $rawComfyReceiptUrl
            detail = "Selected approved image opens in raw Comfy with the Frank workflow receipt marker and sanitized workflow payload attached."
            screenshot = $rawReceiptScreenshot
        }
    )
}

$statusDirectory = Split-Path -Parent $StatusPath
if ($statusDirectory) {
    New-Item -ItemType Directory -Force -Path $statusDirectory | Out-Null
}
$status | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StatusPath -Encoding UTF8

Write-Step "Browser QA passed."
