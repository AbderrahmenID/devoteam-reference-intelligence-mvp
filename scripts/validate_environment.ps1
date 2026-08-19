[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontend = Join-Path $projectRoot 'app\frontend'
$configured = if ($env:DEVOTEAM_CONFIG) { $env:DEVOTEAM_CONFIG } else { 'config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml' }
$config = if ([System.IO.Path]::IsPathRooted($configured)) { $configured } else { Join-Path $projectRoot $configured }

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
    & $python -c "from pathlib import Path; import os,yaml,numpy as np,pandas as pd; p=Path(os.environ.get('DEVOTEAM_CONFIG','config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml')); c=yaml.safe_load(p.read_text(encoding='utf-8')); required=[c['data'][k] for k in ('chunks','reference_catalog','bm25_index','bm25_vocabulary','embeddings','chunk_lookup')]; required.extend([c['export']['template_path'],'templates/reference_pack/v1/template_config.yaml','templates/reference_pack/source/OT_DVT_SDSI__OrangeBANK.pdf']); missing=[p for p in required if not Path(p).is_file()]; assert not missing, f'Missing data/template: {missing}'; chunks=pd.read_parquet(c['data']['chunks']); e=np.load(c['data']['embeddings'],mmap_mode='r'); assert e.shape==(len(chunks),768); m=Path(c['model']['local_path']).expanduser(); assert m.is_dir(), f'Missing pinned model: {m}'; assert c['model']['query_prefix']=='query: ' and c['model']['passage_prefix']=='passage: '; assert c['search']['page_sizes']==[10,20,50] and c['search']['safety_ceiling']>161; assert c['hybrid']['candidate_depth']>=len(chunks); assert not c['reranker_enabled']; import fastapi,sentence_transformers,fitz,docx,pptx,reference_pack; print('Python, selected config, data, model, templates and imports: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Python environment validation failed.' }
} finally {
    Pop-Location
}

$pythonVersion = & $python --version
$nodeVersion = & node --version
$npmVersion = & npm --version
Write-Host "Python: $pythonVersion"
Write-Host "Node.js: $nodeVersion | npm: $npmVersion"
$tesseractCommand = Get-Command tesseract -ErrorAction SilentlyContinue
$tesseractCandidates = @(
    $(if ($tesseractCommand) { $tesseractCommand.Source }),
    'C:\Program Files\Tesseract-OCR\tesseract.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Tesseract-OCR\tesseract.exe')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
$tesseractExe = $tesseractCandidates | Select-Object -First 1
$tessdataCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'DevoteamOCR\tessdata'),
    $(if ($tesseractExe) { Join-Path (Split-Path -Parent $tesseractExe) 'tessdata' })
) | Where-Object {
    $_ -and
    (Test-Path -LiteralPath (Join-Path $_ 'fra.traineddata') -PathType Leaf) -and
    (Test-Path -LiteralPath (Join-Path $_ 'eng.traineddata') -PathType Leaf) -and
    (Test-Path -LiteralPath (Join-Path $_ 'ara.traineddata') -PathType Leaf)
}
$tessdata = $tessdataCandidates | Select-Object -First 1
if ($tesseractExe -and $tessdata) {
    $env:TESSDATA_PREFIX = $tessdata
    Write-Host "Tesseract: available at $tesseractExe with fra+eng+ara data at $tessdata"
} elseif ($tesseractExe) {
    Write-Warning "Tesseract is installed at $tesseractExe, but the required fra+eng+ara language data was not found."
} else {
    Write-Warning 'Tesseract is absent. Retrieval and digital-PDF extraction work; scanned-page OCR preview is unavailable.'
}
$libreOffice = 'C:\Program Files\LibreOffice\program\soffice.exe'
if (Test-Path -LiteralPath $libreOffice -PathType Leaf) {
    Write-Host "LibreOffice: available at $libreOffice"
} else {
    Write-Warning 'LibreOffice is absent. Reference-pack PPTX generation works, but PDF conversion will return a warning.'
}
Write-Host 'Environment validation passed.' -ForegroundColor Green
