$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$results = @()
. (Join-Path $PSScriptRoot "_node-tools.ps1")   # sets $Npm / $Npx next to node.exe

# Python checks run only in the documented component virtual environments
# (docs/LOCAL_SETUP.md). There is deliberately no fallback to a bare system
# Python: it lacks the pinned packages, so its results are not the gate.
$BackendPython = Join-Path $root "backend\.venv\Scripts\python.exe"
$MlPython = Join-Path $root "ml\.venv\Scripts\python.exe"

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
# Preflight — both component interpreters must exist before any check runs.
# The message names only repository-relative paths and the setup command.
# ---------------------------------------------------------------------------
$missing = @()
if (-not (Test-Path $BackendPython)) {
    $missing += "backend/.venv is missing. Create it (EXT-001/EXT-114): py -3.11 -m venv backend\.venv; " +
        "backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt"
}
if (-not (Test-Path $MlPython)) {
    $missing += "ml/.venv is missing. Create it (EXT-001/EXT-114): py -3.11 -m venv ml\.venv; " +
        "ml\.venv\Scripts\python.exe -m pip install -r ml\requirements.txt -r ml\requirements-dev.txt"
}
if ($missing.Count -gt 0) {
    Write-Host "`nPREFLIGHT FAILED: no check was run; bare system Python is never used instead."
    $missing | ForEach-Object { Write-Host "  - $_" }
    exit 2
}

# ---------------------------------------------------------------------------
# Tier 1 — the standard-library safety suites, run in the component venvs.
# ---------------------------------------------------------------------------
Write-Host "`n=== Tier 1: standard-library safety suites (component venvs) ==="

Invoke-Check "ML suite: dialogue, guardrails, SVI, firewalls (ml/.venv)" $root `
    "& '$MlPython' -m unittest discover -s ml/tests -t . -q" $null

Invoke-Check "Backend safety: fan-out, consent, timeline leakage, contract mirror (backend/.venv)" $root `
    "& '$BackendPython' -m unittest discover -s backend/tests -t . -q" $null

Invoke-Check "Mobile assessment-leakage and i18n" $root `
    "node --test `"mobile/tests/*.test.js`"" $null

# ---------------------------------------------------------------------------
# Tier 2 — requires the EXT-001 installs. Reports BLOCKED rather than weakening the check.
# ---------------------------------------------------------------------------
Write-Host "`n=== Tier 2: requires installed EXT-001 dependencies ==="

Invoke-Check "Backend test suite (pytest, backend/.venv)" (Join-Path $root "backend") `
    "& '$BackendPython' -m pytest -q" $null

Invoke-Check "Backend lint (Ruff, backend/.venv)" (Join-Path $root "backend") `
    "& '$BackendPython' -m ruff check ." $null

# ml/requirements-dev.txt carries no linter; the backend's pinned Ruff checks ml/.
Invoke-Check "ML lint (backend/.venv Ruff over ml/)" $root `
    "& '$BackendPython' -m ruff check ml" $null

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
Write-Host "`nOutstanding: S0, S9, SX and SH fixed scripts are not approved (docs/dialogue/STATES.md)."

if ($failed -gt 0 -or $blocked -gt 0) { exit 1 } else { exit 0 }
