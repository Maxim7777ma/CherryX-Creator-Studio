$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
Write-Host "Starting CherryX Telegram bot"
.\.venv\Scripts\python.exe -m src.bot
