$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:PERSISTENT_JOB_QUEUE = "1"
$workerOut = Join-Path $root "worker.out.log"
$workerErr = Join-Path $root "worker.err.log"
$existingWorker = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*manage.py run_worker*" -and $_.CommandLine -like "*$root*" } | Select-Object -First 1
if (-not $existingWorker) {
    Write-Host "Starting CherryX persistent worker"
    Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "manage.py","run_worker" -WorkingDirectory $root -RedirectStandardOutput $workerOut -RedirectStandardError $workerErr -WindowStyle Hidden
}
Write-Host "Starting CherryX Creator Studio on http://127.0.0.1:8000"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
