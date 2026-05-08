# WK52 R1 Orchestrator — validate then run
# Double-click this file (or right-click → Run with PowerShell) from the Kingdom folder.
# Agents 03 + 08 will be dispatched in parallel as cloud agents.

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== WK52 R1: Validating round wk52_r1_plumbing_and_ux ===" -ForegroundColor Cyan
npx tsx tools/ai_studio_orchestrator/src/cli.ts validate `
  --cwd . `
  --sprint wk52_attachment_phase3_radar_alerts_memorial `
  --round wk52_r1_plumbing_and_ux

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "VALIDATE FAILED (exit $LASTEXITCODE) — fix ownership stops before running." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "=== Validate PASSED — launching cloud agents 03 + 08 ===" -ForegroundColor Green
npx tsx tools/ai_studio_orchestrator/src/cli.ts run `
  --cwd . `
  --sprint wk52_attachment_phase3_radar_alerts_memorial `
  --round wk52_r1_plumbing_and_ux

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "RUN exited with code $LASTEXITCODE — check ledger under tools/ai_studio_orchestrator/runs/" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "=== R1 dispatched successfully. ===" -ForegroundColor Green
    Write-Host "Check agent logs under .cursor/plans/agent_logs/ for completion receipts."
    Write-Host "When both 03 and 08 show status=complete, run run_wk52_r2.ps1"
}

Read-Host "Press Enter to exit"
