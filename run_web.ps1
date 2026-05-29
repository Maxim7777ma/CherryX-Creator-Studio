$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
.\.venv\Scripts\uvicorn src.web:app --host 127.0.0.1 --port 8000

