param(
    [int]$Port = 8190
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message, [string]$Color = "Magenta")
    Write-Host "[Frank Create Stop] $Message" -ForegroundColor $Color
}

function Get-FrankServerProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            ($_.Name -like "python*") -and
            ($_.CommandLine -match '(^|\s)main\.py(\s|$)') -and
            ($_.CommandLine -match "(^|\s)--port\s+$Port(\s|$)")
        }
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$processes = @(Get-FrankServerProcess)
if (!$processes.Count) {
    Write-Step "No Frank Create server process found on port $Port." "Yellow"
    exit 0
}

foreach ($process in $processes) {
    Write-Step "Stopping process $($process.ProcessId) on port $Port..."
    Stop-Process -Id $process.ProcessId -Force
}

$suffix = if ($processes.Count -eq 1) { "" } else { "es" }
Write-Step "Stopped $($processes.Count) Frank Create process$suffix on port $Port." "Green"
exit 0
