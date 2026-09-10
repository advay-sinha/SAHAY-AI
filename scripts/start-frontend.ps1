$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "_node-tools.ps1")
Set-Location (Join-Path $root "frontend")
if (-not (Test-Path "node_modules")) { throw "frontend dependencies are missing. Run: cd frontend; npm install (EXT-001 pins)." }
& $Npm run dev
