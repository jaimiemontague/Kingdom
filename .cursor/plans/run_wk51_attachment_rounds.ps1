<#
  WK51 — Pin + Recall MVP. Chains validate + run for PM hub rounds wk51_r1..wk51_r6 (R6 = Pin button visibility + screenshot proof).
  From repo root:
    $env:CURSOR_API_KEY = "crsr_..."
    powershell -File .cursor/plans/run_wk51_attachment_rounds.ps1

  -DryRunValidate: validate all rounds without launching SDK agents.
#>
param(
    [switch] $DryRunValidate,
    [switch] $SkipValidate
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$Sprint = "wk51_attachment_ux_phase3"
$Rounds = @(
    "wk51_r1_design_guardrails",
    "wk51_r2_data_engine_plumbing",
    "wk51_r3_ui_pin_recall",
    "wk51_r4_qa_perf",
    "wk51_r5_verify_qa_after_pm_impl",
    "wk51_r6_pin_visible_fix"
)

$cli = Join-Path $RepoRoot "tools\ai_studio_orchestrator\src\cli.ts"

if ($DryRunValidate) {
    foreach ($round in $Rounds) {
        Write-Host "=== validate $round ===" -ForegroundColor Cyan
        npx tsx $cli validate --sprint $Sprint --round $round
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Write-Host "All WK51 validates OK." -ForegroundColor Green
    exit 0
}

foreach ($round in $Rounds) {
    Write-Host ""
    Write-Host "=== Sprint=$Sprint Round=$round ===" -ForegroundColor Cyan

    if (-not $SkipValidate) {
        npx tsx $cli validate --sprint $Sprint --round $round
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Validate failed for $round" -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }

    npx tsx $cli run --sprint $Sprint --round $round
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Run stopped after $round (exit $LASTEXITCODE)." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "WK51 orchestrator chain completed all rounds." -ForegroundColor Green
exit 0
