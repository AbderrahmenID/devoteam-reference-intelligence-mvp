[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontend = Join-Path $projectRoot 'app\frontend'
$failures = [System.Collections.Generic.List[string]]::new()
$env:USE_TF = '0'
$env:TRANSFORMERS_NO_TF = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'

function Write-Check {
    param([string]$Status, [string]$Label, [string]$Detail)
    $color = if ($Status -eq 'PASS') { 'Green' } elseif ($Status -eq 'WARN') { 'Yellow' } else { 'Red' }
    Write-Host ("[{0}] {1}: {2}" -f $Status, $Label, $Detail) -ForegroundColor $color
}

function Add-Failure {
    param([string]$Label, [string]$Detail)
    $failures.Add("${Label}: ${Detail}")
    Write-Check 'FAIL' $Label $Detail
}

Write-Host 'Devoteam Reference Intelligence preflight' -ForegroundColor Cyan
Write-Host "Repository: $projectRoot"

$systemPython = Get-Command py, python -ErrorAction SilentlyContinue | Select-Object -First 1
if ($systemPython) { Write-Check 'PASS' 'Python launcher' $systemPython.Source } else { Add-Failure 'Python launcher' 'Python 3.10 or 3.11 is required.' }

if (Test-Path -LiteralPath $python -PathType Leaf) {
    $pythonVersion = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
    $pythonMinor = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($pythonMinor -in @('3.10', '3.11')) { Write-Check 'PASS' 'Project Python' $pythonVersion } else { Add-Failure 'Project Python' "Unsupported version $pythonVersion; use 3.10 or 3.11." }
    & $python -c "import fastapi, uvicorn, pandas, pyarrow, numpy, torch, sentence_transformers, fitz, pypdf, PIL, docx, pptx, yaml, pytest, httpx"
    if ($LASTEXITCODE -eq 0) { Write-Check 'PASS' 'Python packages' 'Required runtime and test imports are available.' } else { Add-Failure 'Python packages' 'Run .\scripts\setup.ps1.' }
} else {
    Add-Failure 'Project virtual environment' 'Missing .venv; run .\scripts\setup.ps1.'
}

$node = Get-Command node -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($node) {
    $nodeText = (& $node.Source --version).Trim()
    $nodeVersion = [version]$nodeText.TrimStart('v')
    if ($nodeVersion -ge [version]'20.9.0') { Write-Check 'PASS' 'Node.js' $nodeText } else { Add-Failure 'Node.js' "$nodeText is too old; Node.js 20.9+ is required." }
} else { Add-Failure 'Node.js' 'Node.js 20.9+ is required.' }
if ($npm) { Write-Check 'PASS' 'npm' ((& npm --version).Trim()) } else { Add-Failure 'npm' 'npm is required.' }

$nextBinary = Join-Path $frontend 'node_modules\next\dist\bin\next'
if (Test-Path -LiteralPath $nextBinary -PathType Leaf) { Write-Check 'PASS' 'Frontend dependencies' 'Installed from package-lock.json.' } else { Add-Failure 'Frontend dependencies' 'Run .\scripts\setup.ps1 or npm ci in app\frontend.' }

$requiredRuntime = @(
    'data\chunks.parquet',
    'data\reference_catalog.parquet',
    'data\indexes\bm25_index.npz',
    'data\indexes\bm25_vocabulary.json',
    'data\indexes\embeddings.npy',
    'data\indexes\chunk_lookup.parquet',
    'data\DATA_MANIFEST.json',
    'data\source_metadata\PHASE_4_MANIFEST.json',
    'data\indexes\PHASE_5_MANIFEST.json',
    'data\indexes\retrieval_runtime.json',
    'data\V1_RUNTIME_ASSET_HASHES.json',
    'data\versions\v2\chunks.parquet',
    'data\versions\v2\reference_catalog.parquet',
    'data\versions\v2\indexes\bm25_index.npz',
    'data\versions\v2\indexes\bm25_vocabulary.json',
    'data\versions\v2\indexes\embeddings.npy',
    'data\versions\v2\indexes\chunk_lookup.parquet',
    'data\versions\v2\V2_MIGRATION_MANIFEST.json',
    'data\versions\v2\quarantined_chunks.parquet',
    'data\versions\v2\chunk_policy.parquet',
    'data\versions\v2\V1_TO_V2_CHUNK_MAP.csv',
    'data\versions\v2\page_repair_provenance.parquet'
)
$requiredTemplates = @(
    'templates\reference_template.docx',
    'templates\reference_pack\source\OT_DVT_SDSI__OrangeBANK.pdf',
    'templates\reference_pack\source\references sapmple and template.pptx',
    'templates\reference_pack\derived\orange_pdf_pages_10_29.pptx',
    'templates\reference_pack\derived\orange_pdf_pages_10_29.json',
    'templates\reference_pack\qwen_studio\template_registry.yaml',
    'templates\reference_pack\qwen_studio\template_d_mapping.yaml',
    'templates\reference_pack\v1\template_config.yaml',
    'templates\reference_pack\v1\assets\devoteam_logo.png'
)
$missingRuntime = @($requiredRuntime | Where-Object { -not (Test-Path -LiteralPath (Join-Path $projectRoot $_) -PathType Leaf) })
$missingTemplates = @($requiredTemplates | Where-Object { -not (Test-Path -LiteralPath (Join-Path $projectRoot $_) -PathType Leaf) })
if ($missingRuntime.Count -eq 0) { Write-Check 'PASS' 'Runtime corpus/indexes' "$($requiredRuntime.Count) required files found." } else { Add-Failure 'Runtime corpus/indexes' ("Missing: " + ($missingRuntime -join ', ')) }
if ($missingTemplates.Count -eq 0) { Write-Check 'PASS' 'Presentation templates' "$($requiredTemplates.Count) required files found." } else { Add-Failure 'Presentation templates' ("Missing: " + ($missingTemplates -join ', ')) }

$templateHashes = @{
    'templates\reference_pack\source\OT_DVT_SDSI__OrangeBANK.pdf' = 'BC01334088C95C3796F1B98586E4980C66FD084C45174EEC23FF03195BB39334'
    'templates\reference_pack\source\references sapmple and template.pptx' = 'B8DBEA1191E2FA88F672F65BBF37424A7951F70AF5BC0E5BD7A253F21565C831'
}
foreach ($entry in $templateHashes.GetEnumerator()) {
    $path = Join-Path $projectRoot $entry.Key
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        if ($actual -eq $entry.Value) { Write-Check 'PASS' 'Template hash' $entry.Key } else { Add-Failure 'Template hash' "$($entry.Key) does not match the approved source hash." }
    }
}

if (Test-Path -LiteralPath $python -PathType Leaf) {
    $configured = if ($env:DEVOTEAM_CONFIG) { $env:DEVOTEAM_CONFIG } else { 'config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml' }
    $configPath = if ([System.IO.Path]::IsPathRooted($configured)) { $configured } else { Join-Path $projectRoot $configured }
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        $e5Path = (& $python -c "from pathlib import Path; import yaml,sys; c=yaml.safe_load(Path(sys.argv[1]).read_text(encoding='utf-8')); print(Path(c['model']['local_path']).expanduser().resolve())" $configPath).Trim()
        if (Test-Path -LiteralPath $e5Path -PathType Container) { Write-Check 'PASS' 'Pinned multilingual E5 model' $e5Path } else { Add-Failure 'Pinned multilingual E5 model' 'Install the pinned intfloat/multilingual-e5-base revision documented in README.md.' }
    } else { Add-Failure 'Configuration' "Missing $configured." }
}

$ollamaUrl = if ($env:REFERENCE_NARRATIVE_OLLAMA_URL) { $env:REFERENCE_NARRATIVE_OLLAMA_URL.TrimEnd('/') } else { 'http://127.0.0.1:11434' }
$ollamaModel = if ($env:REFERENCE_NARRATIVE_MODEL) { $env:REFERENCE_NARRATIVE_MODEL } else { 'qwen3.5:9b' }
try {
    $tags = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -TimeoutSec 5
    $modelNames = @($tags.models | ForEach-Object { if ($_.name) { $_.name } elseif ($_.model) { $_.model } })
    if ($modelNames -contains $ollamaModel) { Write-Check 'PASS' 'Ollama model' $ollamaModel } else { Add-Failure 'Ollama model' "$ollamaModel is not installed; run 'ollama pull $ollamaModel'." }
} catch { Add-Failure 'Ollama' "Not reachable at $ollamaUrl." }

$libreOfficeCandidates = @(
    (Get-Command soffice -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
    $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'LibreOffice\program\soffice.exe' }),
    $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'LibreOffice\program\soffice.exe' })
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
$libreOffice = $libreOfficeCandidates | Select-Object -First 1
if ($libreOffice) { Write-Check 'PASS' 'LibreOffice' $libreOffice } else { Add-Failure 'LibreOffice' 'Install LibreOffice and ensure soffice is on PATH for PDF output.' }

if ($failures.Count -gt 0) {
    Write-Host "Preflight failed with $($failures.Count) issue(s)." -ForegroundColor Red
    exit 1
}
Write-Host 'Preflight passed.' -ForegroundColor Green
exit 0
