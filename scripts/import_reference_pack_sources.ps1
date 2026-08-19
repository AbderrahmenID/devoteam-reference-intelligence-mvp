[CmdletBinding()]
param(
    [string]$SourceRoot = 'C:\Users\abder\Downloads\Devoteam_AI_Workspace\Devoteam_AI_CLEAN_PIPELINE\data\snapshots\20260714T154731Z_129ff982c8\raw\evidence'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$resolvedSource = (Resolve-Path -LiteralPath $SourceRoot).Path
$destination = Join-Path $projectRoot '.runtime\reference_pack_sources\raw\evidence'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -Path (Join-Path $resolvedSource '*') -Destination $destination -Force
$files = Get-ChildItem -LiteralPath $destination -File
Write-Host "Imported $($files.Count) read-only source documents into the MVP runtime cache."
