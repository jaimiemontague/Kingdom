# WK52 R2 Orchestrator — validate then run (run AFTER R1 agents 03+08 complete)
# Dispatches Agent 10 (perf consult) + Agent 11 (QA gates + screenshots) in parallel.

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== WK52 R2: Validating round wk52_r2_perf_qa ===" -ForegroundColor Cyan
npx tsx tools/ai_studio_orchestrator/src/cli.ts validate `
  --cwd . `
  --sprint wk52_attachment_phase3_radar_alerts_memorial `
  --round wk52_r2_perf_qa

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "VALIDATE FAILED (exit $LASTEXITCODE) — fix ownership stops before running." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "=== Validate PASSED — launching cloud agents 10 + 11 ===" -ForegroundColor Green
npx tsx tools/ai_studio_orchestrator/src/cli.ts run `
  --cwd . `
  --sprint wk52_attachment_phase3_radar_alerts_memorial `
  --round wk52_r2_perf_qa

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "RUN exited with code $LASTEXITCODE — check ledger under tools/ai_studio_orchestrator/runs/" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "=== R2 dispatched successfully. ===" -ForegroundColor Green
    Write-Host "When Agent 11 log shows status=complete, run: python main.py --provider mock"
    Write-Host "Use the 16-step checklist in Agent 11's pm_human_retest_request log field."
}

Read-Host "Press Enter to exit"
