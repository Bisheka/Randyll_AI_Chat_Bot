# Randyll AI Agent - no-Docker local run (Windows)
# Starts FastAPI (uvicorn, port 8000) + Next.js (port 3000) using the built-in
# local vector store. No Docker, no Qdrant server needed.
#   .\scripts\run-local.ps1          # start (builds frontend on first run)
#   .\scripts\run-local.ps1 -Stop    # stop both
param([switch]$Stop)

$Root = Split-Path $PSScriptRoot -Parent
$RunDir = Join-Path $Root ".local-run"
$PidFile = Join-Path $RunDir "pids.json"
New-Item -ItemType Directory -Force $RunDir | Out-Null

if ($Stop) {
    if (Test-Path $PidFile) {
        (Get-Content $PidFile | ConvertFrom-Json) | ForEach-Object {
            taskkill /PID $_ /T /F 2>$null | Out-Null }  # /T: kill child processes too (npm -> node)
        Remove-Item $PidFile
        Write-Host "Stopped backend + frontend."
    } else { Write-Host "Nothing running (no pid file)." }
    return
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "venv not found. Run: py -3.11 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt" }
if (-not (Test-Path (Join-Path $Root ".env"))) { Write-Warning "No .env found - copy .env.example to .env and add your API key(s). Continuing with offline answers." }

# Frontend: install + build once
$Frontend = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $Frontend ".next"))) {
    Push-Location $Frontend
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Pop-Location
}

# Apply .env values (incl. empty ones) over any stale shell environment,
# e.g. an old OPENAI_API_KEY exported globally would otherwise win.
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)=(.*)$') { Set-Item -Path ("Env:" + $Matches[1]) -Value $Matches[2].Trim() }
    }
}
$env:PYTHONPATH = Join-Path $Root "backend"
$env:QDRANT_URL = ""   # empty -> local vector store (backend/data/vector_store.json)
$pids = @()

$backend = Start-Process -FilePath $Python -ArgumentList "-m","uvicorn","app.api.main:app","--port","8000" `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $RunDir "backend.log") -RedirectStandardError (Join-Path $RunDir "backend.err.log")
$pids += $backend.Id

$frontend = Start-Process -FilePath "npm.cmd" -ArgumentList "start" `
    -WorkingDirectory $Frontend -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $RunDir "frontend.log") -RedirectStandardError (Join-Path $RunDir "frontend.err.log")
$pids += $frontend.Id

$pids | ConvertTo-Json | Set-Content $PidFile

for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep 2
    try { $h = Invoke-RestMethod "http://localhost:8000/api/health" -TimeoutSec 3; break } catch {}
}
if ($h) { Write-Host ("Backend OK: {0} | vectors: {1} ({2} points) | LLM: {3}" -f $h.status, $h.vector_store, $h.indexed_points, $h.llm_provider) }
else { Write-Warning "Backend not responding yet - check .local-run\backend.err.log" }

for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep 2
    try { if ((Invoke-WebRequest "http://localhost:3000" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) { $webOk = $true; break } } catch {}
}
if ($webOk) { Write-Host "Frontend OK: http://localhost:3000  (admin: http://localhost:3000/admin)" }
else { Write-Warning "Frontend not responding yet - check .local-run\frontend.err.log" }

Write-Host "Stop with: .\scripts\run-local.ps1 -Stop"

