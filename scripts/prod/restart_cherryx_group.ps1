param(
    [string]$TaskPrefix = "CherryX"
)

$tasks = @(
    "$TaskPrefix Web",
    "$TaskPrefix Worker",
    "$TaskPrefix Bot"
)

foreach ($task in $tasks) {
    schtasks /End /TN $task 2>$null | Out-Null
}

Start-Sleep -Seconds 2

foreach ($task in $tasks) {
    schtasks /Run /TN $task | Out-Null
    Write-Host "Started $task"
}
