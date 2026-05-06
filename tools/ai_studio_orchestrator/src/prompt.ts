import { REQUIRED_MODEL_ID, type AgentRunSpec, type CompletionReceipt, type RoundContext, type RuntimeMode } from "./types.js";

export function buildWorkerPrompt(context: RoundContext, agent: AgentRunSpec, completionCommand: string, runtime: RuntimeMode = "local"): string {
  const isCloud = runtime === "cloud";

  // Cloud-only bootstrap block — must run FIRST before any other step.
  const cloudBootstrap = isCloud ? [
    "══════════════════════════════════════════════════════",
    "CLOUD BOOTSTRAP — RUN THESE COMMANDS BEFORE ANYTHING ELSE",
    "══════════════════════════════════════════════════════",
    "You are running in a cloud environment. The orchestrator CLI must be installed before you can signal completion.",
    "```powershell",
    "npm --prefix tools/ai_studio_orchestrator install --silent",
    "```",
    "Do not proceed with your assignment until npm install completes successfully.",
    "",
  ] : [];

  // Receipt command block — shown prominently at the top AND repeated at the end.
  const receiptBlock = [
    "══════════════════════════════════════════════════════",
    "⚠️  REQUIRED COMPLETION COMMAND — DO NOT SKIP",
    "══════════════════════════════════════════════════════",
    "This is the LAST thing you do before ending your session.",
    "Run from the repo root AFTER updating your agent log AND" + (isCloud ? " committing+pushing your work (see CLOUD COMMIT CONTRACT below)." : " running all required gates."),
    "Do not change --token, --sprint, --round, or --agent. You may update --summary.",
    "```powershell",
    completionCommand,
    "```",
    "If you do not run this command, the orchestrator cannot proceed to the next wave.",
  ];

  // Cloud commit contract removed — the orchestrator's --auto-push flag on the
  // complete command handles git add/commit/push automatically.
  // Agents only need to run the completion command.

  return [
    `You are Agent ${agent.id}. Please onboard first, then follow these instructions.`,
    "",
    ...cloudBootstrap,
    ...receiptBlock,
    "",
    "MANDATORY ONBOARDING ORDER:",
    "1. Read `AGENTS.md`.",
    "2. Read `.cursor/rules/01-studio-onboarding.mdc`.",
    "3. Read `.cursor/rules/10-orchestrator-logging-contract.mdc`.",
    "4. Read your role-specific onboarding rule under `.cursor/rules/agent-NN-...-onboarding.mdc`.",
    "5. Read the PM hub sprint/round named below.",
    "6. Skim your own agent log for this sprint/round if present.",
    "7. Only then begin the assignment.",
    "",
    "ORCHESTRATOR POLICY:",
    `- You are running under Cursor SDK automation and must use ${REQUIRED_MODEL_ID}.`,
    `- Do not request, select, or spawn a non-${REQUIRED_MODEL_ID} model.`,
    "- If you create subagents, they must inherit this Composer 2 parent or explicitly use Composer 2.",
    "- Follow your role boundaries from AGENTS.md and .cursor/rules.",
    "- Write only to files you own unless your assignment explicitly allows a cross-domain change.",
    "- Update your own agent log exactly as required by `.cursor/rules/10-orchestrator-logging-contract.mdc`.",
    "- Your run is not complete until your log exists at `sprints[SPRINT_ID].rounds[ROUND_ID]` and validates with `python -m json.tool`.",
    "- Do not bump versions or ask Jaimie for manual playtest unless your PM prompt requires a human gate.",
    isCloud
      ? "- You MUST run the completion command shown above. The orchestrator will automatically commit and push your work as part of that command."
      : "- Before your final response, run the exact completion command shown above. This receipt is the orchestrator trigger for the verifier and next wave.",
    "",
    "SPRINT:",
    context.sprintId,
    "",
    "ROUND:",
    context.roundId,
    "",
    "UNIVERSAL PROMPT:",
    context.universalPrompt || "(none provided)",
    "",
    `YOUR AGENT ${agent.id} PROMPT:`,
    agent.prompt,
    "",
    "REPORTING:",
    "- End with a concise status summary.",
    "- Include exact commands and exit codes.",
    "- Include the agent log path and exact sprint/round entry you wrote.",
    "- If blocked, state the owner agent or human gate needed.",
    "",
    "══════════════════════════════════════════════════════",
    "⚠️  REMINDER — REQUIRED COMPLETION COMMAND (run this last):",
    "══════════════════════════════════════════════════════",
    "```powershell",
    completionCommand,
    "```",
  ].join("\n");
}

export function buildVerifierPrompt(receipt: CompletionReceipt, receiptPath: string, verificationCommand: string): string {
  return [
    "You are Agent 12 acting as the Orchestrator Log Reader / Verifier. Please onboard first, then follow these instructions.",
    "",
    "MANDATORY ONBOARDING ORDER:",
    "1. Read `AGENTS.md`.",
    "2. Read `.cursor/rules/01-studio-onboarding.mdc`.",
    "3. Read `.cursor/rules/10-orchestrator-logging-contract.mdc`.",
    "4. Read `.cursor/rules/agent-12-toolsdevex-onboarding.mdc`.",
    "",
    "ORCHESTRATOR POLICY:",
    `- This verification run must use ${REQUIRED_MODEL_ID}.`,
    `- Do not request, select, or spawn a non-${REQUIRED_MODEL_ID} model.`,
    "- Do not edit game code.",
    "- Your job is to verify the worker receipt/log contract and write a verification receipt.",
    "",
    "READ:",
    `- Completion receipt: ${receiptPath}`,
    `- Worker agent: ${receipt.agent_id}`,
    `- Sprint/Round: ${receipt.sprint_id} / ${receipt.round_id}`,
    `- Claimed log path: ${receipt.claimed_log_path ?? "(not provided)"}`,
    "",
    "REQUIRED VERIFICATION COMMAND:",
    "Run this from the repo root. It writes the verification receipt the orchestrator waits for.",
    "```powershell",
    verificationCommand,
    "```",
    "",
    "REPORTING:",
    "- End with a concise verifier status.",
    "- Do not fix the worker's game code.",
    "- If the log is malformed or incomplete, let the verification receipt say `needs_log_repair`.",
  ].join("\n");
}

export function buildPmSynthesisPrompt(
  context: RoundContext,
  ledgerPath: string,
  completedAgents: string[],
  note?: string,
): string {
  return [
    "You are Agent 01. Please onboard first, then follow these instructions.",
    "",
    "MANDATORY ONBOARDING ORDER:",
    "1. Read `AGENTS.md`.",
    "2. Read `.cursor/rules/01-studio-onboarding.mdc`.",
    "3. Read `.cursor/rules/10-orchestrator-logging-contract.mdc`.",
    "4. Read `.cursor/rules/agent-01-pm-onboarding.mdc`.",
    "5. Read the PM hub sprint/round named below.",
    "",
    "ORCHESTRATOR POLICY:",
    `- This synthesis run must use ${REQUIRED_MODEL_ID}.`,
    `- Do not request, select, or spawn a non-${REQUIRED_MODEL_ID} model.`,
    "- You may edit only PM-owned planning/log/rule files.",
    "- Do not edit game, tools, assets, tests, config.py, main.py, or requirements.txt.",
    "",
    "TASK:",
    "Synthesize the completed automated worker wave and decide the next PM action.",
    "",
    "READ:",
    `- Ledger: ${ledgerPath}`,
    "- PM hub: .cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json",
    ...completedAgents.map((id) => `- Agent ${id} log under .cursor/plans/agent_logs/`),
    ...(note ? ["", "HUMAN / ORCHESTRATOR NOTE:", note] : []),
    "",
    "UPDATE:",
    `- Sprint: ${context.sprintId}`,
    `- Round: ${context.roundId}`,
    "- If needed, update Agent 01 PM hub with blockers, bug tickets, next actions, and the next wave.",
    "",
    "STOP CONDITIONS:",
    "- Stop for Jaimie before manual playtest, visual approval, version bump, commit, or push.",
    "- If gates failed, assign the owner agent and do not mark the sprint complete.",
  ].join("\n");
}
