[CmdletBinding()]
param([string]$BackendUrl = 'http://127.0.0.1:8000')

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

function Invoke-SmokeSearch([string]$Label, [string]$Query) {
    $payload = @{ query = $Query; top_k = 3 } | ConvertTo-Json -Compress
    $response = Invoke-RestMethod -Method Post -Uri "$BackendUrl/api/search" -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 30
    if ($response.result_count -gt 3) { throw "$Label returned more than three references." }
    foreach ($result in $response.results) {
        if (-not $result.supporting_passage -or -not $result.source_document -or -not $result.source_page -or -not $result.citation_uri) {
            throw "$Label returned a result without complete evidence citation."
        }
    }
    Write-Host "${Label}: reason=$($response.abstention_reason), results=$($response.result_count), language=$($response.detected_language)"
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

Write-Host 'Demo checks passed. Inputs are technical smoke queries, not expert relevance labels.' -ForegroundColor Green
