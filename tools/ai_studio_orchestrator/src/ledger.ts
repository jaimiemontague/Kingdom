import { mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  type CompletionReceipt,
  REQUIRED_MODEL_ID,
  type CliOptions,
  type LedgerAgentRun,
  type LedgerWave,
  type RunLedger,
  type RunStatus,
  type VerificationReceipt,
  type WaveSpec,
} from "./types.js";

export async function createLedger(
  options: CliOptions,
  waves: WaveSpec[],
  pmHubPath: string,
): Promise<{ ledger: RunLedger; path: string }> {
  const now = timestamp();
  const ledger: RunLedger = {
    schema_version: "1.0",
    created_at: now,
    updated_at: now,
    sprint_id: options.sprint ?? "",
    round_id: options.round ?? "",
    runtime: options.runtime,
    mode: options.mode,
    required_model: REQUIRED_MODEL_ID,
    pm_hub_path: pmHubPath,
    cwd: options.cwd,
    dry_run: options.dryRun,
    waves: waves.map(toLedgerWave),
    stops: [],
  };
  const ledgerDir = path.resolve(options.cwd, options.ledgerDir);
  await mkdir(ledgerDir, { recursive: true });
  const filePath = path.join(
    ledgerDir,
    `${safeName(ledger.sprint_id)}__${safeName(ledger.round_id)}__${Date.now()}.json`,
  );
  await saveLedger(filePath, ledger);
  return { ledger, path: filePath };
}

export async function saveLedger(filePath: string, ledger: RunLedger): Promise<void> {
  ledger.updated_at = timestamp();
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(ledger, null, 2)}\n`, "utf8");
}

export async function loadLedger(filePath: string): Promise<RunLedger> {
  return JSON.parse(await readFile(filePath, "utf8")) as RunLedger;
}

export async function latestLedgerPath(ledgerDir: string): Promise<string | undefined> {
  let entries: string[];
  try {
    entries = await readdir(ledgerDir);
  } catch {
    return undefined;
  }
  const jsonFiles = entries.filter((entry) => entry.endsWith(".json"));
  if (jsonFiles.length === 0) {
    return undefined;
  }
  const withStats = await Promise.all(
    jsonFiles.map(async (entry) => {
      const fullPath = path.join(ledgerDir, entry);
      const info = await stat(fullPath);
      return { fullPath, mtimeMs: info.mtimeMs };
    }),
  );
  withStats.sort((left, right) => left.mtimeMs - right.mtimeMs);
  return withStats.at(-1)?.fullPath;
}

export function setWaveStatus(wave: LedgerWave, status: RunStatus): void {
  wave.status = status;
}

export function findLedgerAgent(ledgerWave: LedgerWave, agentId: string): LedgerAgentRun {
  const found = ledgerWave.agents.find((agent) => agent.agent_id === agentId);
  if (!found) {
    throw new Error(`Ledger agent not found: ${agentId}`);
  }
  return found;
}

export function summarizeLedger(ledger: RunLedger): string {
  const lines = [
    `Sprint: ${ledger.sprint_id}`,
    `Round: ${ledger.round_id}`,
    `Runtime: ${ledger.runtime}`,
    `Mode: ${ledger.mode}`,
    `Model: ${ledger.required_model}`,
    `Dry run: ${ledger.dry_run}`,
    "",
    "Waves:",
  ];

  for (const wave of ledger.waves) {
    lines.push(`- ${wave.id}: ${wave.status}${wave.human_gate ? ` (human: ${wave.human_gate})` : ""}`);
    for (const agent of wave.agents) {
      lines.push(
        `  - Agent ${agent.agent_id}: ${agent.status}, model=${agent.model}` +
          `${agent.completion_token ? `, token=${agent.completion_token}` : ""}` +
          `${agent.run_id ? `, run=${agent.run_id}` : ""}` +
          `${agent.completion_receipt_path ? `, receipt=${agent.completion_receipt_path}` : ""}` +
          `${agent.verification_status ? `, verification=${agent.verification_status}` : ""}` +
          `${agent.log_check ? `, log=${agent.log_check}` : ""}` +
          `${agent.log_check_reason && agent.log_check !== "passed" ? `, log_reason=${agent.log_check_reason}` : ""}` +
          `${agent.error ? `, error=${agent.error}` : ""}`,
      );
    }
  }

  if (ledger.stops.length > 0) {
    lines.push("", "Stops:");
    for (const stop of ledger.stops) {
      lines.push(`- ${stop}`);
    }
  }

  return lines.join("\n");
}

export async function writeDashboard(ledgerDir: string, outputPath?: string): Promise<string> {
  const latest = await latestLedgerPath(ledgerDir);
  if (!latest) {
    throw new Error(`No ledgers found in ${ledgerDir}`);
  }
  const ledger = await loadLedger(latest);
  const target = outputPath ?? path.join(ledgerDir, "dashboard.md");
  const body = [
    "# AI Studio Orchestrator Dashboard",
    "",
    `Generated: ${timestamp()}`,
    "",
    summarizeLedger(ledger),
    "",
    `Ledger: ${latest}`,
  ].join("\n");
  await writeFile(target, `${body}\n`, "utf8");
  return target;
}

export function inboxDir(cwd: string, ledgerDir: string): string {
  return path.join(path.resolve(cwd, ledgerDir), "inbox");
}

export function completionReceiptPath(cwd: string, ledgerDir: string, token: string): string {
  return path.join(inboxDir(cwd, ledgerDir), `${safeName(token)}.completion.json`);
}

export function verificationReceiptPath(cwd: string, ledgerDir: string, token: string): string {
  return path.join(inboxDir(cwd, ledgerDir), `${safeName(token)}.verification.json`);
}

export async function saveCompletionReceipt(
  cwd: string,
  ledgerDir: string,
  receipt: CompletionReceipt,
): Promise<string> {
  const target = completionReceiptPath(cwd, ledgerDir, receipt.token);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(receipt, null, 2)}\n`, "utf8");
  return target;
}

export async function loadCompletionReceipt(filePath: string): Promise<CompletionReceipt> {
  return JSON.parse(await readFile(filePath, "utf8")) as CompletionReceipt;
}

export async function saveVerificationReceipt(
  cwd: string,
  ledgerDir: string,
  receipt: VerificationReceipt,
): Promise<string> {
  const target = verificationReceiptPath(cwd, ledgerDir, receipt.token);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(receipt, null, 2)}\n`, "utf8");
  return target;
}

export async function loadVerificationReceipt(filePath: string): Promise<VerificationReceipt> {
  return JSON.parse(await readFile(filePath, "utf8")) as VerificationReceipt;
}

function toLedgerWave(wave: WaveSpec): LedgerWave {
  return {
    id: wave.id,
    parallel: wave.parallel,
    status: wave.humanGate ? "pending" : "pending",
    human_gate: wave.humanGate,
    agents: wave.agents.map((agent) => ({
      agent_id: agent.id,
      status: "pending",
      model: REQUIRED_MODEL_ID,
    })),
  };
}

function timestamp(): string {
  return new Date().toISOString();
}

function safeName(value: string): string {
  return value.replace(/[^a-zA-Z0-9_.-]+/g, "_") || "unknown";
}
