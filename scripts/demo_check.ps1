[CmdletBinding()]
param([string]$BackendUrl = 'http://127.0.0.1:8000')

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

function Invoke-SmokeSearch([string]$Label, [string]$Query) {
    $payload = @{ query = $Query; page = 1; page_size = 20; sort = 'relevance' } | ConvertTo-Json -Compress
    $response = Invoke-RestMethod -Method Post -Uri "$BackendUrl/api/search" -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 30
    if ($response.result_count -gt 20) { throw "$Label exceeded the requested page size." }
    foreach ($result in $response.results) {
        if (-not $result.supporting_passage -or -not $result.source_document -or -not $result.source_page -or -not $result.citation_uri) {
            throw "$Label returned a result without complete evidence citation."
        }
        if (-not $result.match_details -or $result.match_details.Count -eq 0) {
            throw "$Label returned a result without a professional match explanation."
        }
        if ($result.match_reasons | Where-Object { $_ -match '^Exact terms:' }) {
            throw "$Label exposed the deprecated raw exact-term explanation."
        }
        if ($result.supporting_passage -match '^(?i:passage|query)\s*:') {
            throw "$Label exposed retrieval-only text instead of display evidence."
        }
    }
    Write-Host "${Label}: reason=$($response.abstention_reason), total=$($response.total_count), page_results=$($response.result_count), language=$($response.detected_language)"
    return $response
}

$health = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 10
if ($health.status -ne 'ok') { throw "Backend is not healthy: $($health.status)" }

$frenchQuery = '"R\u00e9f\u00e9rences de plan de continuit\u00e9 d\u2019activit\u00e9 pour une banque"' | ConvertFrom-Json
$arabicQuery = '"\u0645\u0631\u0627\u062c\u0639 \u062d\u0648\u0644 \u0627\u0633\u062a\u0645\u0631\u0627\u0631\u064a\u0629 \u0627\u0644\u0623\u0639\u0645\u0627\u0644 \u0644\u0644\u0628\u0646\u0648\u0643"' | ConvertFrom-Json
$mixedQuery = '"PCA \u0644\u0644\u0628\u0646\u0648\u0643 en Tunisie"' | ConvertFrom-Json
$negativeQuery = '"recette de cuisine pour g\u00e2teau au chocolat"' | ConvertFrom-Json

$french = Invoke-SmokeSearch 'French UTF-8' $frenchQuery
$english = Invoke-SmokeSearch 'English UTF-8' 'Bank business continuity planning references'
$arabic = Invoke-SmokeSearch 'Arabic UTF-8' $arabicQuery
$mixed = Invoke-SmokeSearch 'Mixed Arabic/French' $mixedQuery
foreach ($supported in @($french, $english, $arabic, $mixed)) {
    if ($supported.abstained -or $supported.result_count -eq 0) { throw 'A multilingual technical smoke query unexpectedly abstained.' }
}

$negative = Invoke-SmokeSearch 'Explicit abstention' $negativeQuery
if (-not $negative.abstained -or $negative.result_count -ne 0) { throw 'Unsupported query did not produce explicit zero-result abstention.' }

$invalidRejected = $false
try {
    $bad = @{ query = 'PCA'; filters = @{ unsupported_filter = 'fake' } } | ConvertTo-Json -Depth 4 -Compress
    Invoke-RestMethod -Method Post -Uri "$BackendUrl/api/search" -ContentType 'application/json' -Body $bad -TimeoutSec 10 | Out-Null
} catch {
    $status = [int]$_.Exception.Response.StatusCode
    if ($status -eq 422) { $invalidRejected = $true }
}
if (-not $invalidRejected) { throw 'Backend error validation was not preserved as a real HTTP 422 error.' }

$packTitle = '"R\u00e9f\u00e9rences pertinentes pour la mission"' | ConvertFrom-Json
$packSubtitle = '"S\u00e9lection de r\u00e9f\u00e9rences Devoteam"' | ConvertFrom-Json
$packPayload = @{
    title = $packTitle
    client_name = 'Live demo client'
    subtitle = $packSubtitle
    preparation_date = (Get-Date -Format 'yyyy-MM-dd')
    language = 'fr'
    reference_ids = @($french.results[0].reference_id)
    include_summary = $true
    include_reference_details = $true
    include_evidence_annex = $true
    include_logos = $true
    output_formats = @('pptx')
} | ConvertTo-Json -Depth 5 -Compress
$pack = Invoke-RestMethod -Method Post -Uri "$BackendUrl/api/reference-packs" -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($packPayload)) -TimeoutSec 60
if ($pack.status -notin @('completed', 'completed_with_warnings') -or $pack.selected_reference_count -ne 1 -or $pack.slide_count -lt 4) {
    throw 'Reference-pack generation returned an invalid status or slide count.'
}
$packStatus = Invoke-RestMethod -Uri "$BackendUrl/api/reference-packs/$($pack.generation_id)" -TimeoutSec 10
if ($packStatus.generation_id -ne $pack.generation_id) { throw 'Reference-pack status lookup returned the wrong generation.' }
$pptx = Invoke-WebRequest -Uri "$BackendUrl$($pack.pptx_download_url)" -UseBasicParsing -TimeoutSec 30
if ($pptx.RawContentLength -lt 1000) { throw 'Generated PPTX download is unexpectedly small.' }
$manifest = Invoke-RestMethod -Uri "$BackendUrl$($pack.manifest_download_url)" -TimeoutSec 20
if ($manifest.selected_reference_ids.Count -ne 1 -or -not $manifest.source_pages -or -not $manifest.evidence_chunk_ids) {
    throw 'Reference-pack manifest is missing selected-reference or source-page lineage.'
}
Write-Host "Reference pack: generation=$($pack.generation_id), slides=$($pack.slide_count), selected=$($pack.selected_reference_count)"

Write-Host 'Demo checks passed. Inputs are technical smoke queries, not expert relevance labels.' -ForegroundColor Green
