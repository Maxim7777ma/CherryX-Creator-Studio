$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:PERSISTENT_JOB_QUEUE = "1"
Write-Host "Starting CherryX persistent worker"
.\.venv\Scripts\python.exe manage.py run_worker
