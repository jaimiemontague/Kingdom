export const REQUIRED_MODEL_ID = "composer-2" as const;

export type AutomationMode = "manual" | "assist" | "auto_until_human_gate";
export type RuntimeMode = "local" | "cloud";
export type RunStatus =
  | "pending"
  | "running"
  | "finished"
  | "error"
  | "cancelled"
  | "dry_run"
  | "agent_running"
  | "awaiting_completion_receipt"
  | "verifying_receipt"
  | "verified"
  | "needs_log_repair"
  | "needs_pm_decision"
  | "ready_for_next_wave";
export type CompletionStatus = "done" | "blocked" | "failed";
export type VerificationStatus = "verified" | "needs_log_repair" | "needs_pm" | "failed";

export type AgentId = string;

export interface AutomationConfig {
  mode?: AutomationMode;
  runnable_agents?: AgentId[];
  dependencies?: unknown[];
  human_gates?: string[];
  success_signals?: {
    required_log_entries?: boolean;
    required_exit_codes?: number[];
    required_gates?: string[];
  };
  failure_policy?: {
    retry_limit?: number;
    on_failure?: "stop_for_pm" | "retry" | "continue";
  };
  model_policy?: {
    required_model?: string;
    allow_overrides?: boolean;
    human_approved?: boolean;
  };
}

export interface PmRound {
  round_meta?: Record<string, unknown>;
  pm_status_summary?: Record<string, unknown>;
  pm_next_actions_by_agent?: Record<string, unknown>;
  pm_send_list_minimal?: Record<string, unknown>;
  pm_agent_prompts?: Record<string, string>;
  pm_universal_prompt?: string;
  automation?: AutomationConfig;
}

export interface PmSprint {
  sprint_meta?: Record<string, unknown>;
  rounds?: Record<string, PmRound>;
  pm_universal_prompt?: string;
  pm_send_list_minimal?: Record<string, unknown>;
}

export interface PmHub {
  sprints?: Record<string, PmSprint>;
}

export interface RoundContext {
  sprintId: string;
  roundId: string;
  sprint: PmSprint;
  round: PmRound;
  universalPrompt: string;
  agentPrompts: Record<string, string>;
  sendList: Record<string, unknown>;
  automation: AutomationConfig;
}

export interface AgentRunSpec {
  id: AgentId;
  prompt: string;
  intelligence?: string;
  optional?: boolean;
}

export interface WaveSpec {
  id: string;
  parallel: boolean;
  agents: AgentRunSpec[];
  humanGate?: string;
  dependsOn?: string[];
}

export interface RunLedger {
  schema_version: "1.0";
  created_at: string;
  updated_at: string;
  sprint_id: string;
  round_id: string;
  runtime: RuntimeMode;
  mode: AutomationMode;
  required_model: typeof REQUIRED_MODEL_ID;
  pm_hub_path: string;
  cwd: string;
  dry_run: boolean;
  waves: LedgerWave[];
  stops: string[];
}

export interface LedgerWave {
  id: string;
  parallel: boolean;
  status: RunStatus;
  agents: LedgerAgentRun[];
  human_gate?: string;
}

export interface LedgerAgentRun {
  agent_id: AgentId;
  completion_token?: string;
  sdk_agent_id?: string;
  run_id?: string;
  status: RunStatus;
  model: string;
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
  result_excerpt?: string;
  error?: string;
  log_check?: "passed" | "failed" | "skipped";
  log_check_reason?: string;
  completion_receipt_path?: string;
  verification_receipt_path?: string;
  verification_status?: VerificationStatus;
  verification_reason?: string;
}

export interface CompletionReceipt {
  schema_version: "1.0";
  token: string;
  sprint_id: string;
  round_id: string;
  agent_id: AgentId;
  status: CompletionStatus;
  summary: string;
  files_touched: string[];
  commands_run: string[];
  claimed_log_path?: string;
  claimed_log_round?: string;
  timestamp: string;
}

export interface VerificationReceipt {
  schema_version: "1.0";
  token: string;
  completion_token: string;
  sprint_id: string;
  round_id: string;
  agent_id: AgentId;
  status: VerificationStatus;
  reason: string;
  log_check: "passed" | "failed" | "skipped";
  log_check_reason?: string;
  timestamp: string;
}

export interface CliOptions {
  command: string;
  cwd: string;
  pmHub: string;
  sprint?: string;
  round?: string;
  agents?: string[];
  mode: AutomationMode;
  runtime: RuntimeMode;
  dryRun: boolean;
  skipLogCheck: boolean;
  includeOptional: boolean;
  maxActive: number;
  ledgerDir: string;
  ledger?: string;
  note?: string;
  writeDashboard: boolean;
  cloudRepoUrl?: string;
  cloudBranch?: string;
  token?: string;
  verificationToken?: string;
  agent?: string;
  statusValue?: CompletionStatus;
  summary?: string;
  filesTouched?: string[];
  commandsRun?: string[];
  claimedLogPath?: string;
  claimedLogRound?: string;
  receipt?: string;
}
