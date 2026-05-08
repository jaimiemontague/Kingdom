@echo off
cd /d "%~dp0"
echo.
echo === WK52 R1: Validating round wk52_r1_plumbing_and_ux ===
npx tsx tools/ai_studio_orchestrator/src/cli.ts validate --cwd . --sprint wk52_attachment_phase3_radar_alerts_memorial --round wk52_r1_plumbing_and_ux
if %ERRORLEVEL% neq 0 (
    echo.
    echo VALIDATE FAILED -- fix ownership stops before running.
    pause
    exit /b 1
)
echo.
echo === Validate PASSED -- launching cloud agents 03 + 08 ===
npx tsx tools/ai_studio_orchestrator/src/cli.ts run --cwd . --sprint wk52_attachment_phase3_radar_alerts_memorial --round wk52_r1_plumbing_and_ux
if %ERRORLEVEL% neq 0 (
    echo.
    echo RUN exited with errors -- check tools/ai_studio_orchestrator/runs/ for ledger.
) else (
    echo.
    echo === R1 dispatched. Check .cursor/plans/agent_logs/ for completion receipts. ===
    echo When agents 03 and 08 are done, run run_wk52_r2.bat
)
pause
