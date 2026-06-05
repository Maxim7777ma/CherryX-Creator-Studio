$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
Write-Host "Starting CherryX Creator Studio on http://127.0.0.1:8000"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
