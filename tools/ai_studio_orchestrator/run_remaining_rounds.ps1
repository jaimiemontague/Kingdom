<# 
  Chains orchestrator validate + run for multiple PM hub rounds (one round at a time).
  The CLI has no single --rounds flag; this is the supported way to run the "rest"
  of a sprint in one PowerShell invocation.

  Usage (from repo root):
    $env:CURSOR_API_KEY = "crsr_..."
    .\tools\ai_studio_orchestrator\run_remaining_rounds.ps1

  WK47 default: wk47_r2b_sync_integration, then wk47_r3_validation.
#>
param(
    [Parameter(Mandatory = $false)]
    [string] $Sprint = "wk47_unit_instancing_core",

    [Parameter(Mandatory = $false)]
    [string[]] $Rounds = @(
        "wk47_r2b_sync_integration",
        "wk47_r3_validation"
    ),

    [Parameter(Mandatory = $false)]
    [switch] $SkipValidate
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$cli = Join-Path $RepoRoot "tools\ai_studio_orchestrator\src\cli.ts"
if (-not (Test-Path $cli)) {
    throw "Orchestrator CLI not found at $cli"
}

foreach ($round in $Rounds) {
    Write-Host ""
    Write-Host "=== Sprint=$Sprint Round=$round ===" -ForegroundColor Cyan

    if (-not $SkipValidate) {
        npx tsx $cli validate --sprint $Sprint --round $round
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    npx tsx $cli run --sprint $Sprint --round $round
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Stopped after failed run for round $round (exit $LASTEXITCODE)." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "All rounds completed successfully." -ForegroundColor Green
exit 0
