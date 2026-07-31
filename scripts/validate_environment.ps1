[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontend = Join-Path $projectRoot 'app\frontend'
$config = Join-Path $projectRoot 'config.yaml'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Missing MVP virtual environment: $python. See README.md for creation commands."
}
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw "Missing configuration: $config"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js is not installed or not on PATH.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm is not installed or not on PATH.' }
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules') -PathType Container)) {
    throw "Frontend dependencies are missing. Run 'npm install' in $frontend."
}

$env:USE_TF = '0'
$env:TRANSFORMERS_NO_TF = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'

Push-Location $projectRoot
try {
    & $python -c "from pathlib import Path; import json,yaml,numpy as np,pandas as pd; c=yaml.safe_load(Path('config.yaml').read_text(encoding='utf-8')); required=[c['data'][k] for k in ('chunks','reference_catalog','bm25_index','bm25_vocabulary','embeddings','chunk_lookup')]; missing=[p for p in required if not Path(p).is_file()]; assert not missing, f'Missing data: {missing}'; e=np.load(c['data']['embeddings'],mmap_mode='r'); assert e.shape==(1185,768); m=Path(c['model']['local_path']).expanduser(); assert m.is_dir(), f'Missing pinned model: {m}'; assert c['model']['query_prefix']=='query: ' and c['model']['passage_prefix']=='passage: '; assert c['hybrid']['maximum_final_results']==3; assert not c['reranker_enabled']; import fastapi,sentence_transformers,fitz; print('Python, config, data, model and imports: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Python environment validation failed.' }
} finally {
    Pop-Location
}

$pythonVersion = & $python --version
$nodeVersion = & node --version
$npmVersion = & npm --version
Write-Host "Python: $pythonVersion"
Write-Host "Node.js: $nodeVersion | npm: $npmVersion"
if (Get-Command tesseract -ErrorAction SilentlyContinue) {
    Write-Host 'Tesseract: available (offline OCR preview enabled)'
} else {
    Write-Warning 'Tesseract is absent. Retrieval and digital-PDF extraction work; scanned-page OCR preview is unavailable.'
}
Write-Host 'Environment validation passed.' -ForegroundColor Green

