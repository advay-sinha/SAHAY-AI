$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "backend/.venv is missing. Run: py -3.11 -m venv backend\.venv; backend\.venv\Scripts\python.exe -m pip install -r backendequirements.txt -r backendequirements-dev.txt" }
Set-Location (Join-Path $root "backend")
& $python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
