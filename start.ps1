[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$runtime = Join-Path $projectRoot '.runtime'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontend = Join-Path $projectRoot 'app\frontend'
$node = (Get-Command node -ErrorAction Stop).Source

& (Join-Path $projectRoot 'scripts\validate_environment.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Environment validation failed.' }

New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$backendPidFile = Join-Path $runtime 'backend.pid'
$frontendPidFile = Join-Path $runtime 'frontend.pid'
foreach ($pidFile in @($backendPidFile, $frontendPidFile)) {
    if (Test-Path -LiteralPath $pidFile) {
        $savedPid = [int](Get-Content -LiteralPath $pidFile -Raw)
        if (Get-Process -Id $savedPid -ErrorAction SilentlyContinue) {
            throw "A recorded MVP process is already running (PID $savedPid). Run .\stop.ps1 first."
        }
        Remove-Item -LiteralPath $pidFile -Force
    }
}

$configValues = & $python -c "from pathlib import Path; import yaml; c=yaml.safe_load(Path(r'$projectRoot/config.yaml').read_text(encoding='utf-8')); print(c['api']['host']); print(c['api']['port']); print(c['api']['frontend_port'])"
$apiHost = $configValues[0]
$apiPort = [int]$configValues[1]
$frontendPort = [int]$configValues[2]
$backendUrl = "http://${apiHost}:$apiPort"
$frontendUrl = "http://127.0.0.1:$frontendPort"

$env:USE_TF = '0'
$env:TRANSFORMERS_NO_TF = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:NEXT_PUBLIC_API_URL = $backendUrl

$backend = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.api.main:app','--host',$apiHost,'--port',"$apiPort") -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $runtime 'backend.out.log') -RedirectStandardError (Join-Path $runtime 'backend.err.log') -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $backendPidFile -Value $backend.Id -Encoding ascii

try {
    $healthy = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($backend.HasExited) { throw "Backend exited early. See .runtime\backend.err.log." }
        try {
            $health = Invoke-RestMethod -Uri "$backendUrl/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw 'Backend did not become healthy within 30 seconds.' }

    $nextBin = Join-Path $frontend 'node_modules\next\dist\bin\next'
    if (-not (Test-Path -LiteralPath $nextBin -PathType Leaf)) { throw "Next.js binary not found: $nextBin" }
    $frontendProcess = Start-Process -FilePath $node -ArgumentList @("`"$nextBin`"",'dev','--hostname','127.0.0.1','--port',"$frontendPort") -WorkingDirectory $frontend -RedirectStandardOutput (Join-Path $runtime 'frontend.out.log') -RedirectStandardError (Join-Path $runtime 'frontend.err.log') -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $frontendPidFile -Value $frontendProcess.Id -Encoding ascii

    $frontendReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($frontendProcess.HasExited) { throw "Frontend exited early. See .runtime\frontend.err.log." }
        try {
            $response = Invoke-WebRequest -Uri $frontendUrl -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -eq 200) { $frontendReady = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $frontendReady) { throw 'Frontend did not become ready within 30 seconds.' }
} catch {
    if ($frontendProcess -and -not $frontendProcess.HasExited) { Stop-Process -Id $frontendProcess.Id -Force }
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    Remove-Item -LiteralPath $backendPidFile,$frontendPidFile -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host 'Devoteam Reference MVP is ready.' -ForegroundColor Green
Write-Host "Backend: $backendUrl"
Write-Host "Frontend: $frontendUrl"
Write-Host 'Stop only these recorded processes with: .\stop.ps1'
