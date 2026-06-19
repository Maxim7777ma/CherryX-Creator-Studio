param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$HealthUrl = "http://127.0.0.1:8000/health/",
    [int]$HeartbeatMaxAgeSeconds = 180
)

$ErrorActionPreference = "Continue"
Set-Location $Root

$logDir = Join-Path $Root "logs\prod"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "watchdog.log"

function Write-WatchdogLog {
    param([string]$Message)
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] $Message" | Tee-Object -FilePath $log -Append | Out-Null
}

function Stop-CherryXProcess {
    param([string]$Pattern, [string]$Reason)
    $targets = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*$Root*" -and $_.CommandLine -match $Pattern
    }
    foreach ($proc in $targets) {
        Write-WatchdogLog "Stopping PID $($proc.ProcessId) because $Reason"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Test-Heartbeat {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    $age = (Get-Date) - (Get-Item $Path).LastWriteTime
    return $age.TotalSeconds -le $HeartbeatMaxAgeSeconds
}

try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 10
    if ($response.StatusCode -ne 200) {
        Stop-CherryXProcess "manage.py runserver" "web health returned $($response.StatusCode)"
    }
} catch {
    Stop-CherryXProcess "manage.py runserver" "web health failed: $($_.Exception.Message)"
}

$botHeartbeat = Join-Path $Root "data\bot_heartbeat.json"
if (-not (Test-Heartbeat $botHeartbeat)) {
    Stop-CherryXProcess "-m src.bot" "bot heartbeat is stale or missing"
}

$workerHeartbeat = Join-Path $Root "data\worker_heartbeat.json"
if (-not (Test-Heartbeat $workerHeartbeat)) {
    Stop-CherryXProcess "manage.py run_worker" "worker heartbeat is stale or missing"
}

Write-WatchdogLog "Watchdog check complete."
