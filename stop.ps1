[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$runtime = Join-Path $projectRoot '.runtime'
$targets = @(
    @{ Name = 'backend'; PidFile = (Join-Path $runtime 'backend.pid'); Marker = 'app.api.main:app' },
    @{ Name = 'frontend'; PidFile = (Join-Path $runtime 'frontend.pid'); Marker = 'next' }
)

foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target.PidFile -PathType Leaf)) {
        Write-Host "$($target.Name): no recorded PID"
        continue
    }
    $savedPid = [int](Get-Content -LiteralPath $target.PidFile -Raw)
    $process = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
    if ($process) {
        $details = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
        $commandLine = [string]$details.CommandLine
        $belongsToMvp = $commandLine.IndexOf($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and $commandLine.IndexOf($target.Marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        if (-not $belongsToMvp) {
            throw "Refusing to stop PID $savedPid because its command line does not match the recorded MVP $($target.Name) process."
        }
        Stop-Process -Id $savedPid -Force
        Write-Host "$($target.Name): stopped PID $savedPid"
    } else {
        Write-Host "$($target.Name): recorded PID $savedPid is no longer running"
    }
    Remove-Item -LiteralPath $target.PidFile -Force
}

Write-Host 'MVP stop completed.' -ForegroundColor Green
