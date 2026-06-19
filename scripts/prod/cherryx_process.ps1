param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("web", "worker", "bot")]
    [string]$Component,

    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$Python = "",
    [string]$Bind = "127.0.0.1:8000",
    [int]$MinRestartDelaySeconds = 5,
    [int]$MaxRestartDelaySeconds = 300
)

$ErrorActionPreference = "Stop"
Set-Location $Root

if (-not $Python) {
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
}

$logDir = Join-Path $Root "logs\prod"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$env:PERSISTENT_JOB_QUEUE = "1"
$env:PYTHONUNBUFFERED = "1"

function Get-ComponentArgs {
    param([string]$Name)
    switch ($Name) {
        "web" { return @("manage.py", "runserver", $Bind, "--noreload") }
        "worker" { return @("manage.py", "run_worker") }
        "bot" { return @("-m", "src.bot") }
    }
}

$delay = [Math]::Max(1, $MinRestartDelaySeconds)
$maxDelay = [Math]::Max($delay, $MaxRestartDelaySeconds)
$argsList = Get-ComponentArgs $Component

while ($true) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $day = Get-Date -Format "yyyyMMdd"
    $outLog = Join-Path $logDir "$Component-$day.out.log"
    $errLog = Join-Path $logDir "$Component-$day.err.log"

    "[$stamp] Starting $Component: $Python $($argsList -join ' ')" | Tee-Object -FilePath $outLog -Append | Out-Null

    try {
        & $Python @argsList 1>> $outLog 2>> $errLog
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
    } catch {
        $exitCode = 1
        "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] Wrapper error: $($_.Exception.Message)" | Tee-Object -FilePath $errLog -Append | Out-Null
    }

    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$stamp] $Component exited with code $exitCode. Restarting in $delay seconds." | Tee-Object -FilePath $errLog -Append | Out-Null
    Start-Sleep -Seconds $delay
    $delay = [Math]::Min($delay * 2, $maxDelay)
}
