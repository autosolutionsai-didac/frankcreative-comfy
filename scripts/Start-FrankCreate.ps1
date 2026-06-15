param(
    [int]$Port = 8190,
    [switch]$NoBrowser,
    [switch]$NoBuild,
    [switch]$KeepExisting,
    [switch]$ResetDemoData
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[Frank Create] $Message" -ForegroundColor Magenta
}

function Publish-ReadyAndExit {
    Write-Step "Ready: $StudioUrl"
    if (!$NoBrowser) {
        Write-Step "Opening studio in your default browser..."
        try {
            Start-Process $StudioUrl -ErrorAction Stop
        } catch {
            Write-Host "Could not open the browser automatically. Use: $StudioUrl" -ForegroundColor Yellow
        }
    }
    Write-Host ""
    Write-Host "Studio:         $StudioUrl"
    Write-Host "Advanced Graph: http://127.0.0.1:$Port/graph"
    Write-Host "Raw Comfy:      http://127.0.0.1:$Port/comfy/"
    Write-Host "Logs:           $OutLog"
    Write-Host "Errors:         $ErrLog"
    exit 0
}

function Get-FrankServerProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            ($_.Name -like "python*") -and
            ($_.CommandLine -match '(^|\s)main\.py(\s|$)') -and
            ($_.CommandLine -match "(^|\s)--port\s+$Port(\s|$)")
        }
}

function Test-FrankFrontendBuildStale {
    param(
        [string]$FrontendRoot,
        [string]$DistIndex
    )

    if (!(Test-Path -LiteralPath $DistIndex)) {
        return $true
    }

    $distTime = (Get-Item -LiteralPath $DistIndex).LastWriteTimeUtc
    $watchedPaths = @(
        (Join-Path $FrontendRoot "src"),
        (Join-Path $FrontendRoot "index.html"),
        (Join-Path $FrontendRoot "package.json"),
        (Join-Path $FrontendRoot "package-lock.json"),
        (Join-Path $FrontendRoot "tsconfig.json"),
        (Join-Path $FrontendRoot "tsconfig.app.json"),
        (Join-Path $FrontendRoot "vite.config.ts")
    )

    foreach ($path in $watchedPaths) {
        if (!(Test-Path -LiteralPath $path)) {
            continue
        }

        $item = Get-Item -LiteralPath $path
        if ($item.PSIsContainer) {
            $newerFile = Get-ChildItem -LiteralPath $path -Recurse -File |
                Where-Object { $_.LastWriteTimeUtc -gt $distTime } |
                Select-Object -First 1
            if ($newerFile) {
                return $true
            }
        } elseif ($item.LastWriteTimeUtc -gt $distTime) {
            return $true
        }
    }

    return $false
}

function Test-ProviderEnvValueReal {
    param([string]$Value)

    if ($null -eq $Value) {
        return $false
    }

    $text = $Value.Trim().Trim('"').Trim("'")
    if (!$text) {
        return $false
    }

    $normalized = ($text -replace '\s+', ' ').Trim().ToLowerInvariant()
    $placeholders = @(
        "...",
        "<key>",
        "<paste-key>",
        "<paste key>",
        "<your-key>",
        "<your key>",
        "change-me",
        "changeme",
        "example",
        "paste key",
        "paste-key",
        "replace-me",
        "replace_me",
        "todo",
        "your-api-key",
        "your-key",
        "your_key",
        "your_key_here"
    )

    if ($placeholders -contains $normalized) {
        return $false
    }
    if ($normalized.StartsWith("your_") -or $normalized.StartsWith("your-")) {
        return $false
    }
    if ($normalized.StartsWith("paste ") -or $normalized.StartsWith("replace ")) {
        return $false
    }
    if ($normalized.StartsWith("<") -and $normalized.EndsWith(">")) {
        return $false
    }

    return $true
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$FrontendRoot = Join-Path $Root "frank-create"
$DistIndex = Join-Path $FrontendRoot "dist\index.html"
$LogDir = Join-Path $Root "user\frank_create\logs"
$ProviderEnvFile = Join-Path $Root "user\frank_create\provider_keys.env"
$OutLog = Join-Path $LogDir "frank-create-$Port.out.log"
$ErrLog = Join-Path $LogDir "frank-create-$Port.err.log"
$HealthUrl = "http://127.0.0.1:$Port/api/frank/health"
$StudioUrl = "http://127.0.0.1:$Port/"
$ProviderEnvNames = @(
    "GOOGLE_API_KEY",
    "REPLICATE_API_TOKEN",
    "OPENAI_API_KEY"
)

Set-Location $Root
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (Test-Path $ProviderEnvFile) {
    Write-Step "Loading provider keys from user\frank_create\provider_keys.env..."
    Get-Content -Path $ProviderEnvFile | ForEach-Object {
        $line = $_.Trim()
        if (!$line -or $line.StartsWith("#") -or !$line.Contains("=")) {
            return
        }

        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if (!$name -or !(Test-ProviderEnvValueReal -Value $value)) {
            return
        }

        $currentEnv = Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        if (!$currentEnv -or !(Test-ProviderEnvValueReal -Value $currentEnv.Value)) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

$ConfiguredProviderKeys = @($ProviderEnvNames | Where-Object {
    $item = Get-Item -Path "Env:$_" -ErrorAction SilentlyContinue
    $item -and (Test-ProviderEnvValueReal -Value $item.Value)
})
$MissingProviderKeys = @($ProviderEnvNames | Where-Object {
    $item = Get-Item -Path "Env:$_" -ErrorAction SilentlyContinue
    !$item -or !(Test-ProviderEnvValueReal -Value $item.Value)
})
Write-Step "Provider keys configured: $($ConfiguredProviderKeys.Count) / $($ProviderEnvNames.Count)"
if ($MissingProviderKeys.Count) {
    Write-Host "Missing provider keys: $($MissingProviderKeys -join ', ')" -ForegroundColor DarkYellow
}

if (!(Test-Path $Python)) {
    throw "Python virtualenv was not found at $Python. Run the ComfyUI install first."
}

$FrontendNeedsBuild = Test-FrankFrontendBuildStale -FrontendRoot $FrontendRoot -DistIndex $DistIndex
if (!$NoBuild -and $FrontendNeedsBuild) {
    Write-Step "Frontend build missing or stale. Building Frank shell..."
    Push-Location $FrontendRoot
    try {
        if (!(Test-Path "node_modules")) {
            npm install
        }
        npm run build
    } finally {
        Pop-Location
    }
}

if (!(Test-Path $DistIndex)) {
    throw "Frank frontend dist was not found at $DistIndex. Run: cd frank-create; npm install; npm run build"
}

if ($KeepExisting -and !$ResetDemoData) {
    try {
        $health = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
        if ($health.StatusCode -eq 200) {
            Write-Step "Reusing healthy Frank Create server on port $Port..."
            Publish-ReadyAndExit
        }
    } catch {
        Write-Step "No healthy existing server found on port $Port. Starting a new one..."
    }
} else {
    $existing = Get-FrankServerProcess | Select-Object -ExpandProperty ProcessId

    if ($existing) {
        Write-Step "Stopping existing server on port $Port..."
        Stop-Process -Id $existing -Force
        Start-Sleep -Seconds 2
    }
}

if ($ResetDemoData) {
    Write-Step "Resetting Frank demo sessions and seeding a clean starter brief..."
    & $Python "scripts\reset_frank_demo.py"
}

Write-Step "Starting ComfyUI with Frank Create shell on port $Port..."
Remove-Item -LiteralPath $OutLog, $ErrLog -Force -ErrorAction SilentlyContinue
Start-Process `
    -FilePath $Python `
    -ArgumentList @("main.py", "--port", "$Port", "--front-end-root", "frank-create\dist") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog

$deadline = (Get-Date).AddSeconds(60)
do {
    Start-Sleep -Seconds 2
    try {
        $health = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
        if ($health.StatusCode -eq 200) {
            Publish-ReadyAndExit
        }
    } catch {
        if (Test-Path $ErrLog) {
            $recentError = Get-Content -Path $ErrLog -Tail 12 -ErrorAction SilentlyContinue
            if ($recentError) {
                Write-Host ($recentError -join "`n") -ForegroundColor DarkYellow
            }
        }
    }
} while ((Get-Date) -lt $deadline)

throw "Frank Create did not become healthy at $HealthUrl. Check $ErrLog"
