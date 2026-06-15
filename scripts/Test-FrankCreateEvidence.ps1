param(
    [int]$Port = 8190,
    [switch]$StartIfDown
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Launcher = Join-Path $Root "scripts\Start-FrankCreate.ps1"
$EvidenceScript = Join-Path $Root "scripts\frank_demo_evidence.py"
$HealthUrl = "http://127.0.0.1:$Port/api/frank/health"
$BaseUrl = "http://127.0.0.1:$Port"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

function Write-Step {
    param([string]$Message, [string]$Color = "Magenta")
    Write-Host "[Frank Evidence] $Message" -ForegroundColor $Color
}

Set-Location $Root

try {
    Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 8 | Out-Null
    Write-Step "Health OK at $HealthUrl" "Green"
} catch {
    if (!$StartIfDown) {
        Write-Step "Frank Create is not responding at $HealthUrl" "Red"
        Write-Host "Start it with: .\scripts\Start-FrankCreate.ps1 -NoBrowser -NoBuild"
        exit 1
    }

    Write-Step "Frank Create is down. Starting it now..." "Yellow"
    & $Launcher -Port $Port -NoBrowser -NoBuild
}

if (!(Test-Path $Python)) {
    $Python = "python"
}

& $Python $EvidenceScript --base-url $BaseUrl
exit $LASTEXITCODE
