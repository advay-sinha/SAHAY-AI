$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "_node-tools.ps1")
Set-Location (Join-Path $root "mobile")
if (-not (Test-Path "node_modules")) { throw "mobile dependencies are missing. Run: cd mobile; npm install; npx expo install --check (EXT-001 pins)." }
& $Npx expo start --dev-client
