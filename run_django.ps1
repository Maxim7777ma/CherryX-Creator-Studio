$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
