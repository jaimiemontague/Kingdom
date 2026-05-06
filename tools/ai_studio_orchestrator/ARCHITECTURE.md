# AI Studio Orchestrator Architecture & Run Modes

The Kingdom Sim AI Studio can be operated in three distinct architectural modes. The core difference between these modes dictates **where the orchestrator runs**, **where the agents run**, and **how they communicate completion handshakes** (filesystem vs. Git).

---

## 1. Local-to-Cloud (Default / Recommended)
This is the standard, optimized workflow for running fast, parallelized sprints.

*   **Orchestrator runs on:** Local Machine (Jaimie's workstation)
*   **Agents run on:** Ephemeral Cloud Containers (managed by Cursor SDK)
*   **Command Flag:** `--cloud-repo-url https://github.com/jaimiemontague/Kingdom.git`
*   **Communication:** **Git-Native Polling**

### How it Works:
1.  The local orchestrator launches agents via the SDK, passing them your GitHub repository URL.
2.  Cursor provisions an ephemeral cloud Linux container for each agent and clones the repository.
3.  The cloud agents execute their tasks entirely in the cloud.
4.  **Completion:** The agent runs the completion command `cli.ts complete` **with** the `--auto-push` flag. This command forces the cloud container to commit the receipt and push its changes directly to `origin/main`.
5.  **Polling:** Meanwhile, the local orchestrator periodically runs `git fetch origin` to check for the agent's receipt.
6.  **Post-Flight:** Once the wave finishes, the local orchestrator runs `git merge --ff-only origin/main` to sync your local workstation with the completed cloud work.

*   **Pros:** Highly parallelizable; doesn't freeze your local IDE; ephemeral environments ensure clean builds.
*   **Cons:** Requires Git authentication and relies on network push/pull latency.

---

## 2. All-Local
This mode is useful for debugging, working offline, or if the cloud containers are experiencing latency.

*   **Orchestrator runs on:** Local Machine
*   **Agents run on:** Local Machine (Cursor SDK spawns background processes)
*   **Command Flag:** *(Omit the `--cloud-repo-url` flag)*
*   **Communication:** **Local Filesystem**

### How it Works:
1.  The local orchestrator launches agents locally. No container is provisioned.
2.  The agents execute their tasks directly against your local `C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom` directory.
3.  **Completion:** The agent runs the completion command. Because it is running locally, it simply writes the `.completion.json` receipt directly into the `tools/ai_studio_orchestrator/runs/inbox/` folder.
4.  **Polling:** The orchestrator watches the local filesystem. As soon as the file appears, it proceeds.
5.  **Post-Flight:** No Git merge is necessary because the agents edited your files directly.

*   **Pros:** Instant feedback; no Git pushes required during the run; you can watch the files change in real-time.
*   **Cons:** Agents share the same local filesystem, meaning parallel agents might cause race conditions or Git index locks if they try to edit the same files.

---

## 3. Entirely Cloud
This mode is designed for fully headless CI/CD pipelines (e.g., triggering a sprint from GitHub Actions).

*   **Orchestrator runs on:** Cloud VM / CI Runner
*   **Agents run on:** Ephemeral Cloud Containers
*   **Communication:** **Git-Native Polling**

### How it Works:
1.  A CI pipeline kicks off the orchestrator command in the cloud.
2.  The orchestrator acts exactly like **Local-to-Cloud**, launching agents via the SDK with the `--cloud-repo-url` flag.
3.  **Completion:** Cloud agents push to `origin/main`.
4.  **Polling:** The cloud orchestrator polls `origin/main` via `git fetch`.
5.  **Post-Flight:** The cloud orchestrator syncs its own clone and can run final validation tests before reporting success to the CI pipeline.

*   **Pros:** Zero local compute required; perfect for nightly builds or autonomous scheduling.
*   **Cons:** You cannot easily intervene if a human gate (e.g., visual playtest) is required.

---

## Summary of the Completion Command Handshake

The `npx tsx src/cli.ts complete` command behaves dynamically depending on the environment:

*   If `--cwd` is a Windows path (e.g., `C:\...`), it assumes **Local Mode**, creates a local receipt file, and exits.
*   If `--cwd` is a POSIX path (e.g., `.`), it assumes **Cloud Mode**, configures `git config user.name "Kingdom AI"`, stages the receipt, commits the work, and forcibly pushes the current branch to `origin HEAD:main`. 

> **Important:** When generating commands for the **Local-to-Cloud** default, Agent 01 must ensure the orchestrator is launched with `--auto-push` and `--mode auto_until_human_gate`.
