param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    Check-Exit
}
& .\.venv\Scripts\python.exe -m pip install -e './backend[dev]'
Check-Exit
docker compose up -d --wait postgres
Check-Exit
Push-Location backend
try {
    & ..\.venv\Scripts\python.exe -m alembic upgrade head
    Check-Exit
    & ..\.venv\Scripts\python.exe -m app.seed
    Check-Exit
} finally { Pop-Location }
Push-Location frontend
try { npm.cmd ci; Check-Exit } finally { Pop-Location }
Write-Host 'Setup complete. Run .\scripts\run-local.ps1 next.'
