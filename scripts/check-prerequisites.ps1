$ErrorActionPreference = "Continue"
$commands = @("git", "py", "python", "node", "npm", "ffmpeg", "adb", "docker")
foreach ($name in $commands) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if ($found) { Write-Host "PRESENT  $name  $($found.Source)" }
    else { Write-Host "MISSING  $name" }
}
Write-Host "Missing means unconfigured, not approved for automatic installation."
