[CmdletBinding()]
param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontend = Join-Path $projectRoot 'app\frontend'

& (Join-Path $PSScriptRoot 'validate_environment.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Environment validation failed.' }

$env:USE_TF = '0'
$env:TRANSFORMERS_NO_TF = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'

Push-Location $projectRoot
try {
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
    & $python -m evaluation.evaluate
    if ($LASTEXITCODE -ne 0) { throw 'Evaluation template validation failed.' }
} finally { Pop-Location }

Push-Location $frontend
try {
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    & npm.cmd run lint
    if ($LASTEXITCODE -ne 0) { throw 'Frontend lint failed.' }
    if (-not $SkipBuild) {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    }
} finally { Pop-Location }

Write-Host 'All requested tests passed.' -ForegroundColor Green
