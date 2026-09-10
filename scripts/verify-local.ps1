$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$results = @()
. (Join-Path $PSScriptRoot "_node-tools.ps1")   # sets $Npm / $Npx next to node.exe

function Add-Result($label, $status, $detail) {
    $script:results += [pscustomobject]@{ Check = $label; Status = $status; Detail = $detail }
    Write-Host ("{0,-8} {1} {2}" -f $status, $label, $detail)
}

function Invoke-Check($label, $workingDir, $command, $blockedIfMissing) {
    Write-Host "`n[$label]"
    if ($blockedIfMissing -and -not (Test-Path $blockedIfMissing)) {
        Add-Result $label "BLOCKED" "$blockedIfMissing is missing"
        return
    }
    Push-Location $workingDir
    Invoke-Expression $command
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -eq 0) { Add-Result $label "PASS" "" } else { Add-Result $label "FAIL" "exit $code" }
}

Write-Host "SAHAY-AI local verification"
Write-Host "Nothing here installs or downloads anything."

# ---------------------------------------------------------------------------
# Tier 1 — runs today. The safety-critical modules are standard library only,
# so these need no approved dependency and no virtual environment.
# ---------------------------------------------------------------------------
Write-Host "`n=== Tier 1: no dependencies required ==="

Invoke-Check "ML pure modules (dialogue, guardrails, SVI)" $root `
    "python -m unittest discover -s ml/tests -t . -q" $null

Invoke-Check "Backend safety (fan-out, consent, timeline leakage, contract mirror)" $root `
    "python -m unittest discover -s backend/tests -t . -q" $null

Invoke-Check "Mobile assessment-leakage and i18n" $root `
    "node --test `"mobile/tests/*.test.js`"" $null

# ---------------------------------------------------------------------------
# Tier 2 — requires the EXT-001 installs. Reports BLOCKED rather than weakening the check.
# ---------------------------------------------------------------------------
Write-Host "`n=== Tier 2: requires installed EXT-001 dependencies ==="

Invoke-Check "Backend test suite (pytest)" (Join-Path $root "backend") `
    ".\.venv\Scripts\python.exe -m pytest -q" (Join-Path $root "backend\.venv")

Invoke-Check "Backend lint" (Join-Path $root "backend") `
    ".\.venv\Scripts\python.exe -m ruff check ." (Join-Path $root "backend\.venv")

Invoke-Check "Frontend typecheck and build" (Join-Path $root "frontend") `
    "& '$Npm' run build" (Join-Path $root "frontend\node_modules")

Invoke-Check "Frontend lint" (Join-Path $root "frontend") `
    "& '$Npm' run lint" (Join-Path $root "frontend\node_modules")

Invoke-Check "Frontend contract tests (vitest)" (Join-Path $root "frontend") `
    "& '$Npm' test" (Join-Path $root "frontend\node_modules")

Invoke-Check "Mobile typecheck" (Join-Path $root "mobile") `
    "& '$Npm' run typecheck" (Join-Path $root "mobile\node_modules")

# ---------------------------------------------------------------------------
Write-Host "`n=== Summary ==="
$results | Format-Table -AutoSize

$failed = @($results | Where-Object { $_.Status -eq "FAIL" }).Count
$blocked = @($results | Where-Object { $_.Status -eq "BLOCKED" }).Count
Write-Host ("{0} passed, {1} failed, {2} blocked." -f `
    (@($results | Where-Object { $_.Status -eq "PASS" }).Count), $failed, $blocked)

Write-Host "`nManual checks a script cannot make:"
Write-Host "  - phone reaches the laptop's LAN IPv4 address, not localhost"
Write-Host "  - crisis interrupt reaches a human, by hand, with a real voice"
Write-Host "  - victim client receives no assessment event, observed on the wire"
Write-Host "  - the full demo scenario, on the actual demo machine"
Write-Host "`nOutstanding: S0, S9 and SX fixed scripts are unwritten (docs/dialogue/STATES.md)."

if ($failed -gt 0) { exit 1 } else { exit 0 }
