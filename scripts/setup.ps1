[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $projectRoot '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$frontend = Join-Path $projectRoot 'app\frontend'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $launcher = $null
    $launcherArgs = @()
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) {
        $minor = (& $systemPython.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        if ($minor -in @('3.10', '3.11')) { $launcher = $systemPython.Source }
    }
    if (-not $launcher -and (Get-Command py -ErrorAction SilentlyContinue)) {
        foreach ($candidate in @('-3.11', '-3.10')) {
            & py $candidate -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { $launcher = 'py'; $launcherArgs = @($candidate); break }
        }
    }
    if (-not $launcher) { throw 'Python 3.10 or 3.11 was not found.' }
    & $launcher @launcherArgs -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}

& $python -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw 'Python packaging-tool installation failed.' }
Push-Location $projectRoot
try {
    & $python -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
} finally { Pop-Location }

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm is not installed or not on PATH.' }
Push-Location $frontend
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
} finally { Pop-Location }

Write-Host 'Project dependencies are installed.' -ForegroundColor Green
Write-Host 'External prerequisites are not downloaded automatically.'
Write-Host 'Install the pinned E5 model, Ollama qwen3.5:9b and LibreOffice, then run .\scripts\preflight.ps1.'
