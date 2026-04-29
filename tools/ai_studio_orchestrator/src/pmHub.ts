import { readFile } from "node:fs/promises";
import path from "node:path";
import {
  type AgentRunSpec,
  type PmHub,
  type PmRound,
  type RoundContext,
  type WaveSpec,
} from "./types.js";

const AGENT_LOG_RE = /^agent_(\d{2})_/;

export async function loadRoundContext(
  pmHubPath: string,
  sprintId?: string,
  roundId?: string,
): Promise<RoundContext> {
  const hub = JSON.parse(await readFile(pmHubPath, "utf8")) as PmHub;
  const sprints = hub.sprints ?? {};
  const resolvedSprintId = sprintId ?? lastKey(sprints);
  if (!resolvedSprintId || !sprints[resolvedSprintId]) {
    throw new Error(`Sprint not found: ${sprintId ?? "(latest)"}`);
  }

  const sprint = sprints[resolvedSprintId];
  const rounds = sprint.rounds ?? {};
  const resolvedRoundId = roundId ?? lastKey(rounds);
  if (!resolvedRoundId || !rounds[resolvedRoundId]) {
    throw new Error(`Round not found: ${roundId ?? "(latest)"}`);
  }

  const round = rounds[resolvedRoundId];
  const universalPrompt =
    asString(round.pm_universal_prompt) ??
    asString(sprint.pm_universal_prompt) ??
    "";
  const agentPrompts = round.pm_agent_prompts ?? {};
  const sendList = round.pm_send_list_minimal ?? sprint.pm_send_list_minimal ?? {};

  return {
    sprintId: resolvedSprintId,
    roundId: resolvedRoundId,
    sprint,
    round,
    universalPrompt,
    agentPrompts,
    sendList,
    automation: round.automation ?? {},
  };
}

export function buildWaves(
  context: RoundContext,
  options: {
    selectedAgents?: string[];
    includeOptional?: boolean;
  } = {},
): WaveSpec[] {
  const selected = new Set(options.selectedAgents ?? []);
  const prompts = context.agentPrompts;
  const intelligence = readIntelligenceMap(context.sendList);

  if (selected.size > 0) {
    return [
      {
        id: "selected",
        parallel: true,
        agents: [...selected].map((id) => makeAgentSpec(id, prompts, intelligence)),
      },
    ];
  }

  const dependencyWaves = readAutomationDependencyWaves(context, prompts, intelligence);
  if (dependencyWaves.length > 0) {
    return dependencyWaves;
  }

  const runnable = context.automation.runnable_agents;
  if (Array.isArray(runnable) && runnable.length > 0) {
    return runnable.map((id) => ({
      id: `agent_${String(id)}`,
      parallel: false,
      agents: [makeAgentSpec(String(id), prompts, intelligence)],
    }));
  }

  const waveList = context.sendList.waves;
  if (Array.isArray(waveList) && waveList.length > 0) {
    return waveList.flatMap((wave, index): WaveSpec[] => {
      if (!isRecord(wave)) {
        return [];
      }
      if (wave.human) {
        return [
          {
            id: `human_${String(wave.wave ?? index + 1)}`,
            parallel: false,
            agents: [],
            humanGate: String(wave.human),
          },
        ];
      }
      const agents = readAgentIds(wave.agents).map((id) =>
        makeAgentSpec(id, prompts, intelligence),
      );
      return [
        {
          id: `wave_${String(wave.wave ?? index + 1)}`,
          parallel: Boolean(wave.parallel),
          dependsOn: readStringArray(wave.depends_on),
          agents,
        },
      ];
    });
  }

  const batch = readStringArray(context.sendList.batch_1_parallel);
  const then = readStringArray(context.sendList.then_in_order);
  const optional = options.includeOptional
    ? readStringArray(context.sendList.optional_consult_after)
    : [];
  const waves: WaveSpec[] = [];

  if (batch.length > 0) {
    waves.push({
      id: "batch_1_parallel",
      parallel: true,
      agents: batch.map((id) => makeAgentSpec(id, prompts, intelligence)),
    });
  }

  for (const id of then) {
    waves.push({
      id: `agent_${id}`,
      parallel: false,
      agents: [makeAgentSpec(id, prompts, intelligence)],
    });
  }

  if (optional.length > 0) {
    waves.push({
      id: "optional_consult_after",
      parallel: true,
      agents: optional.map((id) => ({ ...makeAgentSpec(id, prompts, intelligence), optional: true })),
    });
  }

  if (waves.length > 0) {
    return waves;
  }

  return [
    {
      id: "all_prompts",
      parallel: true,
      agents: Object.keys(prompts).map((id) => makeAgentSpec(id, prompts, intelligence)),
    },
  ];
}

export async function hasAgentLogEntry(
  cwd: string,
  agentId: string,
  sprintId: string,
  roundId: string,
): Promise<boolean> {
  return (await validateAgentLogEntry(cwd, agentId, sprintId, roundId)).ok;
}

export interface AgentLogValidation {
  ok: boolean;
  reason?: string;
}

export async function validateAgentLogEntry(
  cwd: string,
  agentId: string,
  sprintId: string,
  roundId: string,
): Promise<AgentLogValidation> {
  const logDir = path.join(cwd, ".cursor", "plans", "agent_logs");
  const { readdir } = await import("node:fs/promises");
  let files: string[];
  try {
    files = await readdir(logDir);
  } catch {
    return { ok: false, reason: `agent log directory not found: ${logDir}` };
  }
  const candidates = files
    .filter((name) => name.endsWith(".json") && AGENT_LOG_RE.exec(name)?.[1] === agentId)
    .sort((left, right) => Number(left.includes("_AUTO")) - Number(right.includes("_AUTO")));
  const file = candidates[0];
  if (!file) {
    return { ok: false, reason: `agent_${agentId} log file not found in ${logDir}` };
  }
  const logPath = path.join(logDir, file);
  try {
    const raw = await readFile(logPath, "utf8");
    const data = JSON.parse(raw) as PmHub;
    const sprint = data.sprints?.[sprintId];
    if (!sprint) {
      return { ok: false, reason: `${file} missing sprints["${sprintId}"]` };
    }
    const round = sprint.rounds?.[roundId];
    if (!round || !isRecord(round)) {
      return { ok: false, reason: `${file} missing sprints["${sprintId}"].rounds["${roundId}"]` };
    }
    const missing = requiredLogFields(roundId).filter((field) => !hasRequiredField(round, field));
    if (missing.length > 0) {
      return {
        ok: false,
        reason: `${file} round ${sprintId}/${roundId} missing required field(s): ${missing.join(", ")}`,
      };
    }
    if (String(round.sprint_id) !== sprintId) {
      return { ok: false, reason: `${file} round has sprint_id=${String(round.sprint_id)} expected ${sprintId}` };
    }
    if (String(round.round_id) !== roundId) {
      return { ok: false, reason: `${file} round has round_id=${String(round.round_id)} expected ${roundId}` };
    }
    return { ok: true };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, reason: `${file} is invalid JSON or unreadable: ${message}` };
  }
}

export function formatWavePlan(waves: WaveSpec[]): string {
  return waves
    .map((wave) => {
      if (wave.humanGate) {
        return `${wave.id}: HUMAN GATE ${wave.humanGate}`;
      }
      const agents = wave.agents.map((agent) => agent.id).join(", ");
      return `${wave.id}: ${wave.parallel ? "parallel" : "sequential"} [${agents}]`;
    })
    .join("\n");
}

function makeAgentSpec(
  id: string,
  prompts: Record<string, string>,
  intelligence: Record<string, string>,
): AgentRunSpec {
  const prompt = prompts[id];
  if (!prompt) {
    throw new Error(`No pm_agent_prompts entry for Agent ${id}`);
  }
  return {
    id,
    prompt,
    intelligence: intelligence[id],
  };
}

function readIntelligenceMap(sendList: Record<string, unknown>): Record<string, string> {
  const value = sendList.intelligence_by_agent;
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(Object.entries(value).map(([key, val]) => [key, String(val)]));
}

function readAutomationDependencyWaves(
  context: RoundContext,
  prompts: Record<string, string>,
  intelligence: Record<string, string>,
): WaveSpec[] {
  const dependencies = context.automation.dependencies;
  if (!Array.isArray(dependencies)) {
    return [];
  }

  return dependencies.flatMap((dependency, index): WaveSpec[] => {
    if (!isRecord(dependency)) {
      return [];
    }
    const agents = readAgentIds(dependency.agents);
    if (agents.length === 0) {
      return [];
    }
    return [
      {
        id: String(dependency.id ?? `automation_${index + 1}`),
        parallel: Boolean(dependency.parallel),
        dependsOn: readStringArray(dependency.after),
        agents: agents.map((id) => makeAgentSpec(id, prompts, intelligence)),
      },
    ];
  });
}

function readAgentIds(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => {
      if (typeof item === "string") {
        return item;
      }
      if (isRecord(item) && typeof item.id === "string") {
        return item.id;
      }
      return undefined;
    })
    .filter((item): item is string => Boolean(item));
}

function requiredLogFields(roundId: string): string[] {
  void roundId;
  return ["sprint_id", "round_id", "status", "what_i_changed", "commands_run", "evidence", "blockers", "follow_ups"];
}

function hasRequiredField(round: Record<string, unknown>, field: string): boolean {
  if (field === "commands_run") {
    return Array.isArray(round.commands_run) || Array.isArray(round.how_to_test);
  }
  if (field === "follow_ups") {
    return Array.isArray(round.follow_ups) || Array.isArray(round.recommended_next_actions);
  }
  return round[field] !== undefined && round[field] !== null;
}

function readStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(String);
  }
  if (typeof value === "string") {
    return [value];
  }
  return [];
}

function lastKey<T>(obj: Record<string, T>): string | undefined {
  const keys = Object.keys(obj);
  return keys.at(-1);
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
