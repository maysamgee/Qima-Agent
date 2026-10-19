$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Split-Path $PSScriptRoot -Parent)).Path
Set-Location $repoRoot
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run bootstrap-local.ps1 first.' }
New-Item -ItemType Directory -Force '.local' | Out-Null
foreach ($port in @(8000, 5173)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is already in use. Existing services were preserved." }
}
docker compose up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not start.' }
Push-Location backend
try {
    & ..\.venv\Scripts\python.exe -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Migrations failed.' }
    & ..\.venv\Scripts\python.exe -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'Seeding failed.' }
} finally { Pop-Location }
$pythonPath = Join-Path $repoRoot '.venv\Scripts\python.exe'
$apiProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log' -WorkingDirectory (Join-Path $repoRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $repoRoot '.local\api.log') -RedirectStandardError (Join-Path $repoRoot '.local\api-error.log') -PassThru
$workerProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m worker.app.main' -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $repoRoot '.local\worker.log') -RedirectStandardError (Join-Path $repoRoot '.local\worker-error.log') -PassThru
$nodePath = (Get-Command node.exe).Source
$webProcess = Start-Process -FilePath $nodePath -ArgumentList 'node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173' -WorkingDirectory (Join-Path $repoRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $repoRoot '.local\frontend.log') -RedirectStandardError (Join-Path $repoRoot '.local\frontend-error.log') -PassThru
@{ api = $apiProcess.Id; worker = $workerProcess.Id; frontend = $webProcess.Id } | ConvertTo-Json | Set-Content -LiteralPath '.local\processes.json'
Write-Host 'Frontend: http://localhost:5173'
Write-Host 'Backend: http://localhost:8000 | API docs: http://localhost:8000/docs'
Write-Host 'Logs and process IDs are in .local. Close only these processes when finished.'
