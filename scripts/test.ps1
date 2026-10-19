$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Check failed with exit code $LASTEXITCODE" } }
Push-Location backend
try {
    & ..\.venv\Scripts\python.exe -m ruff check app tests ../worker
    Check-Exit
    & ..\.venv\Scripts\python.exe -m mypy app ../worker/app
    Check-Exit
    & ..\.venv\Scripts\python.exe -m pytest
    Check-Exit
} finally { Pop-Location }
Push-Location frontend
try {
    npm.cmd run lint
    Check-Exit
    npm.cmd test
    Check-Exit
    npm.cmd run build
    Check-Exit
} finally { Pop-Location }
Write-Host 'All local checks passed. With services running: cd frontend; npm.cmd run test:e2e'
