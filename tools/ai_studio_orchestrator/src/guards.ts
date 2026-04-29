import { execFileSync } from "node:child_process";
import {
  REQUIRED_MODEL_ID,
  type AutomationConfig,
  type RoundContext,
  type WaveSpec,
} from "./types.js";

const HUMAN_GATE_PATTERNS = [
  /manual/i,
  /playtest/i,
  /visual/i,
  /screenshot/i,
  /version bump/i,
  /changelog/i,
  /commit/i,
  /push/i,
];

const GATE_PATTERNS = [
  /qa_smoke\.py\s+--quick/i,
  /validate_assets\.py\s+--report/i,
  /validate_assets\.py\s+--strict/i,
];

const PATH_RE = /(?:`([^`]+)`)|(?<![A-Za-z0-9_])((?:\.cursor|game|ai|tools|assets|tests|docs)\/[A-Za-z0-9_./+ -]+|(?:config\.py|main\.py|requirements\.txt|AGENTS\.md|CHANGELOG\.md))/g;

const OWNERSHIP: Record<string, RegExp[]> = {
  "01": [/^\.cursor\/plans\//, /^\.cursor\/rules\//, /^AGENTS\.md$/],
  "03": [/^game\/sim\//, /^game\/sim_engine\.py$/, /^game\/engine\.py$/, /^game\/game_commands\.py$/, /^game\/input_handler\.py$/, /^game\/graphics\/ursina_/, /^game\/graphics\/pygame_renderer\.py$/, /^assets\/models\//, /^docs\/refactor\//, /^tests\//],
  "05": [/^game\/entities\//, /^game\/systems\//, /^config\.py$/, /^tests\//],
  "06": [/^ai\//, /^tests\//],
  "08": [/^game\/ui\//, /^assets\/ui\//, /^tests\//],
  "09": [/^game\/graphics\//, /^assets\/sprites\//, /^assets\/ui\//, /^docs\/art\//],
  "10": [/^tools\/perf_benchmark\.py$/, /^docs\//],
  "11": [/^tools\/qa_smoke\.py$/, /^tools\/observe_sync\.py$/, /^tools\/determinism_guard\.py$/, /^QA_TEST_PLAN\.md$/, /^RELEASE_QA_CHECKLIST\.md$/],
  "12": [/^tools\//, /^\.cursor\/plans\/ai_studio_automation_contract\.md$/, /^tests\//],
  "13": [/^CHANGELOG\.md$/, /^docs\//, /^\.cursor\/plans\//],
  "14": [/^game\/audio\//, /^assets\/audio\//],
  "15": [/^assets\/prefabs\//, /^assets\/models\//, /^docs\/art\//],
};

export function enforceModelPolicy(config: AutomationConfig): void {
  const policy = config.model_policy ?? {};
  const required = policy.required_model ?? REQUIRED_MODEL_ID;
  if (required !== REQUIRED_MODEL_ID) {
    throw new Error(
      `Model policy requires ${required}; automated studio runs must use ${REQUIRED_MODEL_ID}.`,
    );
  }
  if (policy.allow_overrides && !policy.human_approved) {
    throw new Error("Model overrides require explicit human_approved=true in the PM hub.");
  }
}

export function assertResolvedModel(modelId: string | undefined): void {
  if (modelId && modelId !== REQUIRED_MODEL_ID) {
    throw new Error(`SDK resolved non-Composer model ${modelId}; stopping for cost safety.`);
  }
}

export function findHumanGateStops(context: RoundContext, waves: WaveSpec[]): string[] {
  const stops = new Set<string>();
  for (const gate of context.automation.human_gates ?? []) {
    stops.add(`human gate declared in PM hub: ${gate}`);
  }
  for (const wave of waves) {
    if (wave.humanGate) {
      stops.add(`human wave declared: ${wave.id} -> ${wave.humanGate}`);
    }
    for (const agent of wave.agents) {
      if (HUMAN_GATE_PATTERNS.some((pattern) => pattern.test(agent.prompt))) {
        stops.add(`Agent ${agent.id} prompt mentions a human gate`);
      }
    }
  }
  return [...stops];
}

export function findRequiredGateMentions(waves: WaveSpec[]): string[] {
  const gates = new Set<string>();
  for (const wave of waves) {
    for (const agent of wave.agents) {
      for (const pattern of GATE_PATTERNS) {
        const match = agent.prompt.match(pattern);
        if (match?.[0]) {
          gates.add(match[0]);
        }
      }
    }
  }
  return [...gates];
}

export function findOwnershipStops(waves: WaveSpec[]): string[] {
  const stops = new Set<string>();
  for (const wave of waves) {
    for (const agent of wave.agents) {
      const paths = extractPaths(agent.prompt);
      for (const filePath of paths) {
        if (isReadOnlyReferencePath(filePath) || isSharedGateCommandPath(filePath)) {
          continue;
        }
        if (!isOwnedPath(agent.id, filePath) && looksLikeEditablePath(filePath)) {
          stops.add(`Agent ${agent.id} prompt references non-owned path: ${filePath}`);
        }
      }
    }
  }
  return [...stops];
}

export function readGitStatus(cwd: string): string {
  try {
    return execFileSync("git", ["-C", cwd, "status", "--short"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return `git status unavailable: ${message}`;
  }
}

export function warnIfDirtyTree(cwd: string): string | undefined {
  const status = readGitStatus(cwd);
  if (!status) {
    return undefined;
  }
  return status;
}

function extractPaths(text: string): string[] {
  const results = new Set<string>();
  for (const match of text.matchAll(PATH_RE)) {
    const raw = match[1] ?? match[2];
    if (!raw) {
      continue;
    }
    const cleaned = normalizePathToken(raw);
    results.add(cleaned);
  }
  return [...results];
}

function normalizePathToken(raw: string): string {
  let cleaned = raw
    .replace(/\\/g, "/")
    .replace(/[),.;:]+$/g, "")
    .replace(/^\.?\//, "");
  const extensionMatch = cleaned.match(/^(.+?\.(?:py|json|md|mdc|txt|glb|png|jpg|jpeg|tsx?|plan\.md))/i);
  if (extensionMatch) {
    cleaned = extensionMatch[1];
  } else {
    cleaned = cleaned.split(/\s+/)[0] ?? cleaned;
  }
  return cleaned.replace(/[),.;:]+$/g, "");
}

function isOwnedPath(agentId: string, filePath: string): boolean {
  const rules = OWNERSHIP[agentId];
  if (!rules) {
    return false;
  }
  return rules.some((rule) => rule.test(filePath));
}

function looksLikeEditablePath(filePath: string): boolean {
  return /^(game|ai|tools|assets|tests|\.cursor|config\.py|main\.py|requirements\.txt|AGENTS\.md|CHANGELOG\.md)/.test(filePath);
}

function isReadOnlyReferencePath(filePath: string): boolean {
  return filePath === "AGENTS.md" ||
    filePath.startsWith(".cursor/rules/") ||
    filePath.startsWith(".cursor/plans/agent_logs/") ||
    filePath.startsWith(".cursor/plans/wk") ||
    filePath.startsWith(".cursor/plans/master_plan") ||
    filePath.startsWith(".cursor/plans/ai_studio_automation_contract");
}

function isSharedGateCommandPath(filePath: string): boolean {
  return /^tools\/(qa_smoke|validate_assets|determinism_guard)\.py$/.test(filePath);
}
