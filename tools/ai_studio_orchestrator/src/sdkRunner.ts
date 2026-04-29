import { createHash, randomUUID } from "node:crypto";
import { mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { Agent, type ModelSelection, type SDKAgent } from "@cursor/sdk";
import { REQUIRED_MODEL_ID, type RuntimeMode } from "./types.js";
import { assertResolvedModel } from "./guards.js";

export interface LaunchOptions {
  apiKey: string;
  cwd: string;
  runtime: RuntimeMode;
  name: string;
  prompt: string;
  cloudRepoUrl?: string;
  cloudBranch?: string;
}

export interface LaunchResult {
  sdkAgentId: string;
  runId: string;
  status: string;
  model: string;
  durationMs?: number;
  result?: string;
}

const COMPOSER_MODEL: ModelSelection = { id: REQUIRED_MODEL_ID };

export async function launchAgent(options: LaunchOptions): Promise<LaunchResult> {
  const agent = await createAgent(options);
  try {
    const run = await agent.send(options.prompt);
    for await (const event of run.stream()) {
      if (event.type === "status" && event.status !== "FINISHED") {
        console.error(`[${options.name}] ${event.status}${event.message ? ` ${event.message}` : ""}`);
      }
      if (event.type === "tool_call") {
        console.error(`[${options.name}] tool ${event.status}: ${event.name}`);
      }
    }
    const result = await run.wait();
    const modelId = result.model?.id ?? agent.model?.id ?? REQUIRED_MODEL_ID;
    assertResolvedModel(modelId);
    return {
      sdkAgentId: agent.agentId,
      runId: result.id,
      status: result.status,
      model: modelId,
      durationMs: result.durationMs,
      result: result.result,
    };
  } finally {
    await agent[Symbol.asyncDispose]();
  }
}

export async function createAgent(options: LaunchOptions): Promise<SDKAgent> {
  if (options.runtime === "cloud") {
    if (!options.cloudRepoUrl) {
      throw new Error("--cloud-repo-url is required for cloud runtime");
    }
    return Agent.create({
      apiKey: options.apiKey,
      name: options.name,
      model: COMPOSER_MODEL,
      cloud: {
        repos: [
          {
            url: options.cloudRepoUrl,
            ...(options.cloudBranch ? { startingRef: options.cloudBranch } : {}),
          },
        ],
      },
    });
  }

  const agentId = stableAgentId(options.name);
  await ensureLocalSdkAgentStore(process.cwd(), agentId);

  return Agent.create({
    apiKey: options.apiKey,
    agentId,
    name: options.name,
    model: COMPOSER_MODEL,
    local: { cwd: options.cwd },
  });
}

function stableAgentId(name: string): string {
  return `agent-${createHash("sha256").update(`${name}:${Date.now()}:${randomUUID()}`).digest("hex").slice(0, 40)}`;
}

async function ensureLocalSdkAgentStore(workspacePath: string, agentId: string): Promise<void> {
  const absoluteWorkspace = path.resolve(workspacePath);
  const projectSlug = absoluteWorkspace
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const workspaceHash = createHash("md5").update(absoluteWorkspace).digest("hex");
  const agentStoreDir = path.join(
    os.homedir(),
    ".cursor",
    "projects",
    projectSlug,
    "sdk-agent-store",
    workspaceHash,
    "agents",
    agentId,
  );
  await mkdir(agentStoreDir, { recursive: true });
}
