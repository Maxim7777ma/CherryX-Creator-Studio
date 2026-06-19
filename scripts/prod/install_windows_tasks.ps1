param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$Bind = "127.0.0.1:8000",
    [string]$TaskPrefix = "CherryX",
    [string]$RunAsUser = $env:USERNAME
)

$ErrorActionPreference = "Stop"

$wrapper = Join-Path $Root "scripts\prod\cherryx_process.ps1"
$watchdog = Join-Path $Root "scripts\prod\cherryx_watchdog.ps1"

function Register-CherryXTask {
    param([string]$Name, [string]$Args)
    $taskName = "$TaskPrefix $Name"
    schtasks /Create /TN $taskName /SC ONSTART /RL HIGHEST /RU $RunAsUser /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$wrapper`" $Args" /F
}

Register-CherryXTask "Web" "-Component web -Root `"$Root`" -Bind `"$Bind`""
Register-CherryXTask "Worker" "-Component worker -Root `"$Root`""
Register-CherryXTask "Telegram Bot" "-Component bot -Root `"$Root`""

schtasks /Create /TN "$TaskPrefix Watchdog" /SC MINUTE /MO 1 /RL HIGHEST /RU $RunAsUser /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$watchdog`" -Root `"$Root`" -HealthUrl `"http://$Bind/health/`"" /F

Write-Host "CherryX scheduled tasks installed."
Write-Host "Check with: schtasks /Query /TN `"$TaskPrefix Web`""
