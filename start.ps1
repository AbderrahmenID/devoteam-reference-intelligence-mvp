[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$runtime = Join-Path $projectRoot '.runtime'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontend = Join-Path $projectRoot 'app\frontend'
$node = (Get-Command node -ErrorAction Stop).Source

if (-not $env:DEVOTEAM_CONFIG) {
    $env:DEVOTEAM_CONFIG = 'config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml'
}
if (-not $env:REFERENCE_NARRATIVE_PROVIDER) {
    $env:REFERENCE_NARRATIVE_PROVIDER = 'ollama'
}
if (-not $env:REFERENCE_NARRATIVE_OLLAMA_URL) {
    $env:REFERENCE_NARRATIVE_OLLAMA_URL = 'http://localhost:11434'
}
if (-not $env:REFERENCE_NARRATIVE_MODEL) {
    $env:REFERENCE_NARRATIVE_MODEL = 'qwen3.5:9b'
}
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

# Development output is disposable. Starting clean prevents an interrupted
# Next.js process from leaving stale chunk references behind.
$frontendRoot = [System.IO.Path]::GetFullPath($frontend)
$devOutput = [System.IO.Path]::GetFullPath((Join-Path $frontend '.next-dev'))
$frontendPrefix = $frontendRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $devOutput.StartsWith($frontendPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean frontend output outside the frontend directory: $devOutput"
}
if (Test-Path -LiteralPath $devOutput) {
    Remove-Item -LiteralPath $devOutput -Recurse -Force
}

$configValues = & $python -c "from app.api.settings import load_config; c=load_config(); print(c['api']['host']); print(c['api']['port']); print(c['api']['frontend_port'])"
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

    # Initialize retrieval before the browser can issue concurrent first-use
    # requests. Startup now fails explicitly instead of leaving a fetch error.
    $facets = Invoke-WebRequest -Uri "$backendUrl/api/facets" -TimeoutSec 120 -UseBasicParsing
    if ($facets.StatusCode -ne 200) { throw 'Backend retrieval initialization failed.' }

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
Write-Host "Configuration: $env:DEVOTEAM_CONFIG"
Write-Host 'Stop only these recorded processes with: .\stop.ps1'
