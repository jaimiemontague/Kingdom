#!/usr/bin/env node
import { randomUUID } from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { buildWorkerPrompt, buildPmSynthesisPrompt, buildVerifierPrompt } from "./prompt.js";
import {
  buildWaves,
  formatWavePlan,
  loadRoundContext,
  validateAgentLogEntry,
} from "./pmHub.js";
import {
  createLedger,
  completionReceiptPath,
  findLedgerAgent,
  latestLedgerPath,
  loadCompletionReceipt,
  loadLedger,
  loadVerificationReceipt,
  saveLedger,
  saveCompletionReceipt,
  saveVerificationReceipt,
  setWaveStatus,
  summarizeLedger,
  verificationReceiptPath,
  writeDashboard,
} from "./ledger.js";
import {
  enforceModelPolicy,
  findHumanGateStops,
  findOwnershipStops,
  findRequiredGateMentions,
  warnIfDirtyTree,
} from "./guards.js";
import { launchAgent } from "./sdkRunner.js";
import {
  REQUIRED_MODEL_ID,
  type AgentRunSpec,
  type AutomationMode,
  type CliOptions,
  type CompletionReceipt,
  type LedgerWave,
  type RunLedger,
  type RuntimeMode,
  type VerificationReceipt,
  type WaveSpec,
} from "./types.js";

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  process.chdir(options.cwd);

  switch (options.command) {
    case "validate":
      await validateCommand(options);
      return;
    case "run":
      await runCommand(options);
      return;
    case "synthesize":
      await synthesizeCommand(options);
      return;
    case "status":
      await statusCommand(options);
      return;
    case "complete":
      await completeCommand(options);
      return;
    case "verify-receipt":
      await verifyReceiptCommand(options);
      return;
    case "help":
    default:
      printHelp();
  }
}

async function validateCommand(options: CliOptions): Promise<void> {
  const context = await loadRoundContext(options.pmHub, options.sprint, options.round);
  enforceModelPolicy(context.automation);
  const waves = buildWaves(context, {
    selectedAgents: options.agents,
    includeOptional: options.includeOptional,
  });
  validateDoNotSend(context.sendList, waves, options.agents);
  const ownershipStops = findOwnershipStops(waves);
  console.log(`Sprint: ${context.sprintId}`);
  console.log(`Round: ${context.roundId}`);
  console.log(`Model: ${REQUIRED_MODEL_ID}`);
  console.log(formatWavePlan(waves));
  if (ownershipStops.length > 0) {
    console.log("\nOwnership guard stops:");
    for (const stop of ownershipStops) {
      console.log(`- ${stop}`);
    }
  }
  const gates = findRequiredGateMentions(waves);
  if (gates.length > 0) {
    console.log("\nGate mentions:");
    for (const gate of gates) {
      console.log(`- ${gate}`);
    }
  }
}

async function runCommand(options: CliOptions): Promise<void> {
  const context = await loadRoundContext(options.pmHub, options.sprint, options.round);
  options.sprint = context.sprintId;
  options.round = context.roundId;
  enforceModelPolicy(context.automation);

  const waves = buildWaves(context, {
    selectedAgents: options.agents,
    includeOptional: options.includeOptional,
  });
  validateDoNotSend(context.sendList, waves, options.agents);

  const dirty = warnIfDirtyTree(options.cwd);
  if (dirty) {
    console.error("[guard] Working tree has existing changes. The orchestrator will not commit or push.");
    console.error(dirty);
  }

  const { ledger, path: ledgerPath } = await createLedger(options, waves, options.pmHub);
  const humanStops = findHumanGateStops(context, waves);
  const ownershipStops = findOwnershipStops(waves);
  ledger.stops.push(...humanStops, ...ownershipStops);
  await saveLedger(ledgerPath, ledger);

  console.log(`Ledger: ${ledgerPath}`);
  console.log(`Model policy: ${REQUIRED_MODEL_ID}`);
  console.log(formatWavePlan(waves));

  if (options.dryRun || options.mode === "manual") {
    for (const wave of ledger.waves) {
      wave.status = wave.human_gate ? "pending" : "dry_run";
      for (const agent of wave.agents) {
        agent.status = "dry_run";
      }
    }
    await saveLedger(ledgerPath, ledger);
    console.log("\nDry run complete. No SDK agents launched.");
    return;
  }

  if (ownershipStops.length > 0) {
    throw new Error(`Ownership guard stopped launch:\n${ownershipStops.join("\n")}`);
  }

  requireApiKey();

  for (let index = 0; index < waves.length; index += 1) {
    const wave = waves[index];
    const ledgerWave = ledger.waves[index];
    if (wave.humanGate) {
      ledgerWave.status = "pending";
      ledger.stops.push(`Stopped for human gate: ${wave.humanGate}`);
      await saveLedger(ledgerPath, ledger);
      console.log(`Stopped for human gate: ${wave.humanGate}`);
      break;
    }

    setWaveStatus(ledgerWave, "running");
    await saveLedger(ledgerPath, ledger);

    if (wave.parallel) {
      await runAgentsInBatches(options, context, wave, ledger, ledgerWave, ledgerPath);
    } else {
      for (const agent of wave.agents) {
        await runOneAgent(options, context, agent, ledger, ledgerWave, ledgerPath);
      }
    }

    const failed = ledgerWave.agents.find((agent) =>
      agent.status === "error" ||
      agent.status === "cancelled" ||
      agent.status === "needs_log_repair" ||
      agent.status === "needs_pm_decision"
    );
    setWaveStatus(ledgerWave, failed ? "error" : "finished");
    await saveLedger(ledgerPath, ledger);
    if (failed) {
      ledger.stops.push(`Stopped after ${wave.id}: Agent ${failed.agent_id} status=${failed.status}`);
      await saveLedger(ledgerPath, ledger);
      break;
    }
  }

  console.log("\nRun complete.");
  console.log(summarizeLedger(ledger));
}

async function synthesizeCommand(options: CliOptions): Promise<void> {
  const ledgerPath = options.ledger
    ? path.resolve(options.cwd, options.ledger)
    : await latestLedgerPath(path.resolve(options.cwd, options.ledgerDir));
  if (!ledgerPath) {
    throw new Error("No ledger provided and no latest ledger found.");
  }
  const ledger = await loadLedger(ledgerPath);
  const context = await loadRoundContext(options.pmHub, ledger.sprint_id, ledger.round_id);
  enforceModelPolicy(context.automation);
  const completedAgents = ledger.waves
    .flatMap((wave) => wave.agents)
    .filter((agent) => agent.status === "finished")
    .map((agent) => agent.agent_id);
  const prompt = buildPmSynthesisPrompt(context, ledgerPath, completedAgents, options.note);

  if (options.dryRun || options.mode === "manual") {
    console.log(prompt);
    return;
  }

  requireApiKey();
  const result = await launchAgent({
    apiKey: process.env.CURSOR_API_KEY!,
    cwd: options.cwd,
    runtime: options.runtime,
    name: `Kingdom Agent 01 synthesis - ${ledger.sprint_id}/${ledger.round_id}`,
    prompt,
    cloudRepoUrl: options.cloudRepoUrl,
    cloudBranch: options.cloudBranch,
  });
  console.log(`Agent 01 synthesis status=${result.status} run=${result.runId}`);
}

async function statusCommand(options: CliOptions): Promise<void> {
  const ledgerDir = path.resolve(options.cwd, options.ledgerDir);
  const ledgerPath = options.ledger
    ? path.resolve(options.cwd, options.ledger)
    : await latestLedgerPath(ledgerDir);
  if (!ledgerPath) {
    console.log(`No ledgers found in ${ledgerDir}`);
    return;
  }
  const ledger = await loadLedger(ledgerPath);
  console.log(summarizeLedger(ledger));
  if (options.writeDashboard) {
    const dashboard = await writeDashboard(ledgerDir);
    console.log(`\nDashboard written: ${dashboard}`);
  }
}

async function completeCommand(options: CliOptions): Promise<void> {
  if (!options.token || !options.sprint || !options.round || !options.agent || !options.statusValue) {
    throw new Error("complete requires --token, --sprint, --round, --agent, and --status");
  }
  const receipt: CompletionReceipt = {
    schema_version: "1.0",
    token: options.token,
    sprint_id: options.sprint,
    round_id: options.round,
    agent_id: options.agent,
    status: options.statusValue,
    summary: options.summary ?? "",
    files_touched: options.filesTouched ?? [],
    commands_run: options.commandsRun ?? [],
    claimed_log_path: options.claimedLogPath,
    claimed_log_round: options.claimedLogRound,
    timestamp: new Date().toISOString(),
  };
  const receiptPath = await saveCompletionReceipt(options.cwd, options.ledgerDir, receipt);
  console.log(`Completion receipt written: ${receiptPath}`);
}

async function verifyReceiptCommand(options: CliOptions): Promise<void> {
  if (!options.receipt || !options.token) {
    throw new Error("verify-receipt requires --receipt and --token");
  }
  const receiptPath = path.resolve(options.cwd, options.receipt);
  const completion = await loadCompletionReceipt(receiptPath);
  let status: VerificationReceipt["status"] = "verified";
  let reason = "Completion receipt and claimed agent log verified.";
  let logCheck: VerificationReceipt["log_check"] = "skipped";
  let logReason: string | undefined;

  if (completion.status === "blocked") {
    status = "needs_pm";
    reason = `Worker reported blocked: ${completion.summary}`;
  } else if (completion.status === "failed") {
    status = "failed";
    reason = `Worker reported failed: ${completion.summary}`;
  } else {
    const validation = await validateAgentLogEntry(
      options.cwd,
      completion.agent_id,
      completion.sprint_id,
      completion.round_id,
    );
    logCheck = validation.ok ? "passed" : "failed";
    logReason = validation.reason;
    if (!validation.ok) {
      status = "needs_log_repair";
      reason = validation.reason ?? "Agent log failed validation.";
    }
  }

  const verification: VerificationReceipt = {
    schema_version: "1.0",
    token: options.token,
    completion_token: completion.token,
    sprint_id: completion.sprint_id,
    round_id: completion.round_id,
    agent_id: completion.agent_id,
    status,
    reason,
    log_check: logCheck,
    log_check_reason: logReason,
    timestamp: new Date().toISOString(),
  };
  const verificationPath = await saveVerificationReceipt(options.cwd, options.ledgerDir, verification);
  console.log(`Verification receipt written: ${verificationPath}`);
  console.log(`${status}: ${reason}`);
}

async function runAgentsInBatches(
  options: CliOptions,
  context: Awaited<ReturnType<typeof loadRoundContext>>,
  wave: WaveSpec,
  ledger: RunLedger,
  ledgerWave: LedgerWave,
  ledgerPath: string,
): Promise<void> {
  for (let start = 0; start < wave.agents.length; start += options.maxActive) {
    const batch = wave.agents.slice(start, start + options.maxActive);
    await Promise.all(batch.map((agent) => runOneAgent(options, context, agent, ledger, ledgerWave, ledgerPath)));
  }
}

async function runOneAgent(
  options: CliOptions,
  context: Awaited<ReturnType<typeof loadRoundContext>>,
  agent: AgentRunSpec,
  ledger: RunLedger,
  ledgerWave: LedgerWave,
  ledgerPath: string,
): Promise<void> {
  const ledgerAgent = findLedgerAgent(ledgerWave, agent.id);
  const completionToken = randomUUID();
  ledgerAgent.completion_token = completionToken;
  ledgerAgent.status = "agent_running";
  ledgerAgent.started_at = new Date().toISOString();
  await saveLedger(ledgerPath, ledger);
  const retryLimit = context.automation.failure_policy?.retry_limit ?? 0;

  for (let attempt = 0; attempt <= retryLimit; attempt += 1) {
    try {
      ledgerAgent.error = attempt > 0 ? `retry attempt ${attempt}` : undefined;
      const result = await launchAgent({
        apiKey: process.env.CURSOR_API_KEY!,
        cwd: options.cwd,
        runtime: options.runtime,
        name: `Kingdom Agent ${agent.id} - ${context.sprintId}/${context.roundId}`,
        prompt: buildWorkerPrompt(context, agent, buildCompletionCommand(options, context, agent, completionToken)),
        cloudRepoUrl: options.cloudRepoUrl,
        cloudBranch: options.cloudBranch,
      });
      ledgerAgent.sdk_agent_id = result.sdkAgentId;
      ledgerAgent.run_id = result.runId;
      ledgerAgent.status = result.status === "finished" ? "finished" : "error";
      ledgerAgent.model = result.model;
      ledgerAgent.duration_ms = result.durationMs;
      ledgerAgent.result_excerpt = excerpt(result.result);
      ledgerAgent.finished_at = new Date().toISOString();
      ledgerAgent.status = "awaiting_completion_receipt";
      await saveLedger(ledgerPath, ledger);

      const completion = await waitForCompletionReceipt(options, completionToken);
      if (!completion) {
        ledgerAgent.status = "error";
        ledgerAgent.error = `Completion receipt was not written for token ${completionToken}.`;
        break;
      }
      ledgerAgent.completion_receipt_path = completionReceiptPath(options.cwd, options.ledgerDir, completionToken);
      ledgerAgent.status = "verifying_receipt";
      await saveLedger(ledgerPath, ledger);

      const verification = await runVerifierAgent(options, context, completion, ledgerAgent.completion_receipt_path);
      ledgerAgent.verification_receipt_path = verificationReceiptPath(options.cwd, options.ledgerDir, verification.token);
      ledgerAgent.verification_status = verification.status;
      ledgerAgent.verification_reason = verification.reason;
      ledgerAgent.log_check = verification.log_check;
      ledgerAgent.log_check_reason = verification.log_check_reason;

      if (options.skipLogCheck) {
        ledgerAgent.log_check = "skipped";
      } else if (verification.status === "verified") {
        ledgerAgent.status = "finished";
      } else if (verification.status === "needs_log_repair") {
        ledgerAgent.status = "needs_log_repair";
        ledgerAgent.error = `Verifier requested log repair: ${verification.reason}`;
      } else if (verification.status === "needs_pm") {
        ledgerAgent.status = "needs_pm_decision";
        ledgerAgent.error = `Verifier requested PM decision: ${verification.reason}`;
      } else {
        ledgerAgent.status = "error";
        ledgerAgent.error = `Verifier failed receipt: ${verification.reason}`;
      }
      if (ledgerAgent.status === "finished" || attempt === retryLimit) {
        break;
      }
    } catch (error) {
      ledgerAgent.status = "error";
      ledgerAgent.error = error instanceof Error ? error.message : String(error);
      ledgerAgent.finished_at = new Date().toISOString();
      if (attempt === retryLimit) {
        break;
      }
      await saveLedger(ledgerPath, ledger);
    }
  }

  await saveLedger(ledgerPath, ledger);
}

async function waitForCompletionReceipt(options: CliOptions, token: string): Promise<CompletionReceipt | undefined> {
  const receiptPath = completionReceiptPath(options.cwd, options.ledgerDir, token);
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const receipt = await loadCompletionReceipt(receiptPath);
      if (receipt.token === token) {
        return receipt;
      }
    } catch {
      // keep waiting
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return undefined;
}

async function waitForVerificationReceipt(options: CliOptions, token: string): Promise<VerificationReceipt | undefined> {
  const receiptPath = verificationReceiptPath(options.cwd, options.ledgerDir, token);
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const receipt = await loadVerificationReceipt(receiptPath);
      if (receipt.token === token) {
        return receipt;
      }
    } catch {
      // keep waiting
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return undefined;
}

async function runVerifierAgent(
  options: CliOptions,
  context: Awaited<ReturnType<typeof loadRoundContext>>,
  completion: CompletionReceipt,
  completionPath: string,
): Promise<VerificationReceipt> {
  const verificationToken = randomUUID();
  const verificationCommand = buildVerificationCommand(options, completionPath, verificationToken);
  const result = await launchAgent({
    apiKey: process.env.CURSOR_API_KEY!,
    cwd: options.cwd,
    runtime: options.runtime,
    name: `Kingdom verifier - ${completion.agent_id} - ${context.sprintId}/${context.roundId}`,
    prompt: buildVerifierPrompt(completion, completionPath, verificationCommand),
    cloudRepoUrl: options.cloudRepoUrl,
    cloudBranch: options.cloudBranch,
  });
  if (result.status !== "finished") {
    throw new Error(`Verifier SDK run ended with status ${result.status}`);
  }
  const verification = await waitForVerificationReceipt(options, verificationToken);
  if (!verification) {
    throw new Error(`Verification receipt was not written for token ${verificationToken}`);
  }
  return verification;
}

function validateDoNotSend(
  sendList: Record<string, unknown>,
  waves: WaveSpec[],
  selectedAgents?: string[],
): void {
  const doNotSend = new Set(Array.isArray(sendList.do_not_send) ? sendList.do_not_send.map(String) : []);
  if (doNotSend.size === 0) {
    return;
  }
  const explicit = new Set(selectedAgents ?? []);
  for (const wave of waves) {
    for (const agent of wave.agents) {
      if (doNotSend.has(agent.id) && !explicit.has(agent.id)) {
        throw new Error(`Agent ${agent.id} is listed in do_not_send but was selected by the wave plan.`);
      }
    }
  }
}

function buildCompletionCommand(
  options: CliOptions,
  context: Awaited<ReturnType<typeof loadRoundContext>>,
  agent: AgentRunSpec,
  token: string,
): string {
  const logPath = agentLogPath(agent.id);
  const logRound = `sprints["${context.sprintId}"].rounds["${context.roundId}"]`;
  return [
    "npx tsx",
    quotePs("tools\\ai_studio_orchestrator\\src\\cli.ts"),
    "complete",
    "--cwd",
    quotePs(options.cwd),
    "--sprint",
    quotePs(context.sprintId),
    "--round",
    quotePs(context.roundId),
    "--agent",
    quotePs(agent.id),
    "--token",
    quotePs(token),
    "--status",
    "done",
    "--summary",
    quotePs(`Agent ${agent.id} completed assigned work. Update this summary if blocked or failed.`),
    "--log-path",
    quotePs(logPath),
    "--log-round",
    quotePs(logRound),
  ].join(" ");
}

function buildVerificationCommand(options: CliOptions, receiptPath: string, token: string): string {
  return [
    "npx tsx",
    quotePs("tools\\ai_studio_orchestrator\\src\\cli.ts"),
    "verify-receipt",
    "--cwd",
    quotePs(options.cwd),
    "--receipt",
    quotePs(receiptPath),
    "--token",
    quotePs(token),
  ].join(" ");
}

function quotePs(value: string): string {
  return `"${value.replace(/"/g, '\\"')}"`;
}

function agentLogPath(agentId: string): string {
  const names: Record<string, string> = {
    "01": "agent_01_ExecutiveProducer_PM.json",
    "02": "agent_02_GameDirector_ProductOwner.json",
    "03": "agent_03_TechnicalDirector_Architecture.json",
    "04": "agent_04_NetworkingDeterminism_Lead.json",
    "05": "agent_05_GameplaySystemsDesigner.json",
    "06": "agent_06_AIBehaviorDirector_LLM.json",
    "07": "agent_07_ContentScenarioDirector.json",
    "08": "agent_08_UX_UI_Director.json",
    "09": "agent_09_ArtDirector_Pixel_Animation_VFX.json",
    "10": "agent_10_PerformanceStability_Lead.json",
    "11": "agent_11_QA_TestEngineering_Lead.json",
    "12": "agent_12_ToolsDevEx_Lead.json",
    "13": "agent_13_SteamRelease_Ops_Marketing.json",
    "14": "agent_14_SoundDirector_Audio.json",
    "15": "agent_15_ModelAssembler_KitbashLead.json",
  };
  return `.cursor\\plans\\agent_logs\\${names[agentId] ?? `agent_${agentId}.json`}`;
}

function parseArgs(argv: string[]): CliOptions {
  const command = argv[0] ?? "help";
  const cwd = process.cwd();
  const options: CliOptions = {
    command,
    cwd,
    pmHub: path.join(cwd, ".cursor", "plans", "agent_logs", "agent_01_ExecutiveProducer_PM.json"),
    mode: "assist",
    runtime: "local",
    dryRun: false,
    skipLogCheck: false,
    includeOptional: false,
    maxActive: 3,
    ledgerDir: path.join("tools", "ai_studio_orchestrator", "runs"),
    writeDashboard: false,
  };

  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => {
      const value = argv[i + 1];
      if (!value || value.startsWith("--")) {
        throw new Error(`Expected value after ${arg}`);
      }
      i += 1;
      return value;
    };

    switch (arg) {
      case "--cwd":
        options.cwd = path.resolve(next());
        options.pmHub = path.join(options.cwd, ".cursor", "plans", "agent_logs", "agent_01_ExecutiveProducer_PM.json");
        break;
      case "--pm-hub":
        options.pmHub = path.resolve(options.cwd, next());
        break;
      case "--sprint":
        options.sprint = next();
        break;
      case "--round":
        options.round = next();
        break;
      case "--agents":
        options.agents = next().split(",").map((item) => item.trim()).filter(Boolean);
        break;
      case "--mode":
        options.mode = parseMode(next());
        break;
      case "--runtime":
        options.runtime = parseRuntime(next());
        break;
      case "--dry-run":
        options.dryRun = true;
        break;
      case "--skip-log-check":
        options.skipLogCheck = true;
        break;
      case "--include-optional":
        options.includeOptional = true;
        break;
      case "--max-active":
        options.maxActive = Number.parseInt(next(), 10);
        if (!Number.isFinite(options.maxActive) || options.maxActive < 1) {
          throw new Error("--max-active must be a positive integer");
        }
        break;
      case "--ledger-dir":
        options.ledgerDir = next();
        break;
      case "--ledger":
        options.ledger = next();
        break;
      case "--note":
        options.note = next();
        break;
      case "--token":
        options.token = next();
        break;
      case "--verification-token":
        options.verificationToken = next();
        break;
      case "--agent":
        options.agent = next();
        break;
      case "--status": {
        const status = next();
        if (status !== "done" && status !== "blocked" && status !== "failed") {
          throw new Error("--status must be done, blocked, or failed");
        }
        options.statusValue = status;
        break;
      }
      case "--summary":
        options.summary = next();
        break;
      case "--files":
        options.filesTouched = splitCsv(next());
        break;
      case "--commands":
        options.commandsRun = splitCsv(next());
        break;
      case "--log-path":
        options.claimedLogPath = next();
        break;
      case "--log-round":
        options.claimedLogRound = next();
        break;
      case "--receipt":
        options.receipt = next();
        break;
      case "--write-dashboard":
        options.writeDashboard = true;
        break;
      case "--cloud-repo-url":
        options.cloudRepoUrl = next();
        break;
      case "--cloud-branch":
        options.cloudBranch = next();
        break;
      case "--help":
        options.command = "help";
        break;
      default:
        throw new Error(`Unknown option: ${arg}`);
    }
  }

  options.pmHub = path.resolve(options.pmHub);
  options.ledgerDir = path.resolve(options.cwd, options.ledgerDir);
  return options;
}

function splitCsv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseMode(value: string): AutomationMode {
  if (value === "manual" || value === "assist" || value === "auto_until_human_gate") {
    return value;
  }
  throw new Error(`Unknown mode: ${value}`);
}

function parseRuntime(value: string): RuntimeMode {
  if (value === "local" || value === "cloud") {
    return value;
  }
  throw new Error(`Unknown runtime: ${value}`);
}

function requireApiKey(): void {
  if (!process.env.CURSOR_API_KEY) {
    throw new Error("Set CURSOR_API_KEY before launching SDK agents.");
  }
}

function excerpt(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > 500 ? `${normalized.slice(0, 497)}...` : normalized;
}

function printHelp(): void {
  console.log(`AI Studio Orchestrator

Usage:
  npm run studio -- validate --sprint <id> --round <id>
  npm run studio -- run --sprint <id> --round <id> [--agents 11] [--dry-run]
  npm run studio -- synthesize --ledger <path>
  npm run studio -- status [--write-dashboard]

Options:
  --cwd <path>             Repo root. Defaults to current working directory.
  --pm-hub <path>          PM hub JSON path.
  --sprint <id>            Sprint id. Defaults to latest sprint.
  --round <id>             Round id. Defaults to latest round in sprint.
  --agents <ids>           Comma-separated agent IDs to launch.
  --mode <mode>            manual | assist | auto_until_human_gate.
  --runtime <runtime>      local | cloud.
  --dry-run                Build ledger without launching SDK agents.
  --skip-log-check         Do not require matching agent log entries.
  --include-optional       Include optional consult agents.
  --max-active <n>         Parallel launch cap. Defaults to 3.
  --ledger <path>          Ledger path for status/synthesize.
  --note <text>            Extra human/orchestrator note for synthesis.
  --write-dashboard        Write runs/dashboard.md from latest ledger.
  --cloud-repo-url <url>   Required for cloud runtime.
  --cloud-branch <name>    Optional cloud starting branch.

Model policy:
  All SDK agents are forced to ${REQUIRED_MODEL_ID}.

Run from repo root with:
  npm --prefix tools/ai_studio_orchestrator run studio -- validate --sprint wk46-stage3-lumberjack-builders --round wk46_r0_kickoff
`);
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().then(() => {
    // The local Cursor SDK can leave notifier handles open after a run; this is a CLI, so exit explicitly.
    process.exit(0);
  }).catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Error: ${message}`);
    process.exit(1);
  });
}
