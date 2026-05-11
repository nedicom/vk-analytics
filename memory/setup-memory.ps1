# Run this script on a new device after git clone/pull
# Copies memory files from the repo into Claude Code's memory directory

$projectKey = "c--Users-infin-OneDrive--------------vk"
$memoryDest = "$env:USERPROFILE\.claude\projects\$projectKey\memory"

New-Item -ItemType Directory -Force -Path $memoryDest | Out-Null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Get-ChildItem "$scriptDir\*.md" | ForEach-Object {
    Copy-Item $_.FullName -Destination $memoryDest -Force
    Write-Host "Copied: $($_.Name)"
}

Write-Host "Memory restored to $memoryDest"
