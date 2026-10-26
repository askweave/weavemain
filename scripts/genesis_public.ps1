# PowerShell launcher for Weave / Genesis with Cloudflare Tunnel on native Windows.
#
# Usage:
#   .\scripts\genesis_public.ps1
#   $env:PUBLIC_BASE_URL="https://your-domain.com"; .\scripts\genesis_public.ps1

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# 1. Automatic project root detection
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
Set-Location $ProjectRoot

Write-Host "== Weave / Genesis Launcher ==" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

# 2. Port and directory configuration
$Port = if ($env:GENESIS_PORT) { [int]$env:GENESIS_PORT } else { 8765 }
$DataDir = Join-Path $ProjectRoot "data"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}

# 3. Locate Python executable
$PythonBin = if (Test-Path (Join-Path $ProjectRoot ".venv\Scripts\python.exe")) {
    Join-Path $ProjectRoot ".venv\Scripts\python.exe"
} elseif (Test-Path (Join-Path $ProjectRoot "venv\Scripts\python.exe")) {
    Join-Path $ProjectRoot "venv\Scripts\python.exe"
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { $py.Source } else { $null }
}

if (-not $PythonBin) {
    Write-Error "Python executable not found. Please install Python or activate your virtual environment."
    exit 1
}

# 4. Check port availability
$portInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Error "Port $Port is already in use by process PID $($portInUse.OwningProcess). Terminate it or set GENESIS_PORT to a free port."
    exit 1
}

# 5. Locate cloudflared or verify pre-configured PUBLIC_BASE_URL
$TunnelProc = $null

try {
    if (-not $env:PUBLIC_BASE_URL) {
        Write-Host "Checking for Cloudflare Tunnel (cloudflared)..."
        $CloudflaredBin = $null
        $cfCmd = Get-Command cloudflared -ErrorAction SilentlyContinue
        if ($cfCmd) {
            $CloudflaredBin = $cfCmd.Source
        } else {
            $cfCandidates = @(
                "C:\Program Files (x86)\cloudflared\cloudflared.exe",
                "C:\Program Files\cloudflared\cloudflared.exe",
                (Join-Path $env:LOCALAPPDATA "Programs\cloudflared\cloudflared.exe")
            )
            foreach ($cand in $cfCandidates) {
                if (Test-Path $cand) {
                    $CloudflaredBin = $cand
                    break
                }
            }
        }

        if (-not $CloudflaredBin) {
            Write-Error @"
cloudflared was not found on PATH or standard install paths.
To install Cloudflare Tunnel on Windows, run:
    winget install --id Cloudflare.cloudflared
or download from:
    https://github.com/cloudflare/cloudflared/releases
"@
            exit 1
        }

        Write-Host "Starting Cloudflare Quick Tunnel -> http://127.0.0.1:$Port"
        $LogFile = Join-Path $DataDir "cloudflared.log"
        if (Test-Path $LogFile) { Remove-Item $LogFile -Force }

        $cfPsi = New-Object System.Diagnostics.ProcessStartInfo
        $cfPsi.FileName = $CloudflaredBin
        $cfPsi.Arguments = "tunnel --no-autoupdate --logfile `"$LogFile`" --url http://127.0.0.1:$Port"
        $cfPsi.UseShellExecute = $false
        $cfPsi.CreateNoWindow = $true

        $TunnelProc = [System.Diagnostics.Process]::Start($cfPsi)

        Write-Host "Waiting for tunnel URL (up to 60s)..."
        $TunnelUrl = $null
        $Pattern = 'https://[a-zA-Z0-9-]+\.trycloudflare\.com'

        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 1
            if ($TunnelProc.HasExited) {
                $errLog = if (Test-Path $LogFile) { Get-Content $LogFile -Tail 20 | Out-String } else { "No logs" }
                Write-Error "cloudflared exited unexpectedly with code $($TunnelProc.ExitCode). Log:`n$errLog"
                exit 1
            }
            if (Test-Path $LogFile) {
                try {
                    $fs = [System.IO.File]::Open($LogFile, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
                    $sr = New-Object System.IO.StreamReader($fs)
                    $content = $sr.ReadToEnd()
                    $sr.Close()
                    $fs.Close()
                    if ($content -match $Pattern) {
                        $TunnelUrl = $Matches[0]
                        break
                    }
                } catch {
                    # Log file locked briefly during write
                }
            }
        }

        if (-not $TunnelUrl) {
            Write-Error "Timed out waiting for Cloudflare Tunnel URL. Check log: $LogFile"
            exit 1
        }

        $env:PUBLIC_BASE_URL = $TunnelUrl
    }

    $PublicUrlFile = Join-Path $DataDir "public_url"
    $env:PUBLIC_BASE_URL | Out-File -FilePath $PublicUrlFile -Encoding utf8 -Force

    Write-Host ""
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host "  Weave Public URL:         $env:PUBLIC_BASE_URL" -ForegroundColor Green
    Write-Host "  Meta Webhook Callback URL: $env:PUBLIC_BASE_URL/api/webhooks/whatsapp" -ForegroundColor Yellow
    Write-Host "  Twilio SMS/WhatsApp:      $env:PUBLIC_BASE_URL/api/webhooks/twilio/sms" -ForegroundColor Yellow
    Write-Host "  Phone Web Chat:           $env:PUBLIC_BASE_URL/chat" -ForegroundColor Cyan
    Write-Host "  Dashboard (Local Only):   http://127.0.0.1:$Port" -ForegroundColor Cyan
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host "Starting Weave server..." -ForegroundColor Green

    # Run Weave server process
    & $PythonBin -m genesis serve
} finally {
    if ($TunnelProc -and -not $TunnelProc.HasExited) {
        Write-Host "`nStopping Cloudflare Tunnel (PID $($TunnelProc.Id))..." -ForegroundColor Yellow
        try {
            $TunnelProc.Kill()
            $TunnelProc.WaitForExit(5000)
        } catch {
            # Process may have already exited
        }
    }
}
