param(
    [int]$Port = 8190,
    [switch]$StartIfDown
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Launcher = Join-Path $Root "scripts\Start-FrankCreate.ps1"
$HealthUrl = "http://127.0.0.1:$Port/api/frank/health"
$DoctorUrl = "http://127.0.0.1:$Port/api/frank/demo-doctor"

function Write-Step {
    param([string]$Message, [string]$Color = "Magenta")
    Write-Host "[Frank Create] $Message" -ForegroundColor $Color
}

function Invoke-Json {
    param([string]$Uri)
    return Invoke-RestMethod -Uri $Uri -TimeoutSec 8
}

Set-Location $Root

try {
    $health = Invoke-Json $HealthUrl
    Write-Step "Health OK: $($health.product)" "Green"
} catch {
    if (!$StartIfDown) {
        Write-Step "Frank Create is not responding at $HealthUrl" "Red"
        Write-Host "Start it with: .\scripts\Start-FrankCreate.ps1 -ResetDemoData"
        exit 1
    }

    Write-Step "Frank Create is down. Starting it now..." "Yellow"
    & $Launcher -Port $Port -NoBrowser -NoBuild
}

try {
    $doctor = Invoke-Json $DoctorUrl
} catch {
    if (!$StartIfDown) {
        Write-Step "Demo Doctor is not responding at $DoctorUrl" "Red"
        Write-Host "Restart with: .\scripts\Start-FrankCreate.ps1 -ResetDemoData"
        exit 1
    }

    Write-Step "Demo Doctor route is unavailable. Restarting Frank Create to load the latest extension..." "Yellow"
    & $Launcher -Port $Port -NoBrowser -NoBuild
    $doctor = Invoke-Json $DoctorUrl
}

Write-Step "$($doctor.headline) ($($doctor.status))" ($(if ($doctor.readyForDemo) { "Green" } else { "Red" }))

foreach ($check in $doctor.checks) {
    $color = switch ($check.status) {
        "ready" { "Green" }
        "warning" { "Yellow" }
        default { "Red" }
    }
    Write-Host "[$($check.status)] $($check.label): $($check.detail)" -ForegroundColor $color
    if ($check.action) {
        Write-Host "  -> $($check.action)" -ForegroundColor DarkYellow
    }
}

if (!$doctor.readyForDemo) {
    exit 1
}

exit 0
