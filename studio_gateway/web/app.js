function $(id) { return document.getElementById(id); }

const tokenInput = $("token");
const saveTokenBtn = $("saveToken");
const healthPill = $("health");
let autoPollTimer = null;

function getToken() {
  return localStorage.getItem("studioGatewayToken") || "";
}
function setToken(t) {
  localStorage.setItem("studioGatewayToken", t || "");
}

async function apiFetch(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  const t = getToken();
  if (t) headers["X-Studio-Gateway-Token"] = t;
  if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch { data = text; }
  if (!res.ok) throw new Error((data && data.error) ? data.error : `HTTP ${res.status}`);
  return data;
}

function pretty(obj) {
  return typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

async function refreshHealth() {
  try {
    const data = await apiFetch("/health", { method: "GET" });
    healthPill.textContent = data.ok ? "OK" : "BAD";
    healthPill.classList.toggle("ok", !!data.ok);
    healthPill.classList.toggle("bad", !data.ok);
    $("version").textContent = data.version || "—";
  } catch (e) {
    healthPill.textContent = "OFFLINE";
    healthPill.classList.remove("ok");
    healthPill.classList.add("bad");
  }
}

async function refreshStatus() {
  const st = await apiFetch("/api/status");
  $("job").textContent = st.job && st.job.running ? `${st.job.name}` : "idle";
  await refreshSprints();
}

async function refreshSprints() {
  const data = await apiFetch("/api/sprints");
  const select = $("sprintSelect");
  const existing = select.value;
  select.innerHTML = "";
  const keys = Object.keys(data.sprints || {});
  keys.sort();
  for (const k of keys) {
    const opt = document.createElement("option");
    opt.value = k;
    opt.textContent = `${k} — ${data.sprints[k]}`;
    select.appendChild(opt);
  }
  if (existing && keys.includes(existing)) select.value = existing;
  if (!select.value && keys.length) select.value = keys[0];
  await loadSprintDetail();
}

async function loadSprintDetail() {
  const sid = $("sprintSelect").value;
  if (!sid) { $("sprintDetail").textContent = ""; return; }
  const s = await apiFetch(`/api/sprints/${encodeURIComponent(sid)}`);
  $("sprintDetail").textContent = pretty(s);
  await loadEditorFromSprint(s);
}

async function loadAgents() {
  const data = await apiFetch("/api/agents");
  const container = $("agents");
  container.innerHTML = "";
  for (const a of (data.agents || [])) {
    const id = a.agent_id;
    const label = a.label || id;
    const row = document.createElement("label");
    row.className = "agentCheck";
    row.innerHTML = `<input type="checkbox" data-agent="${id}" /> <span>${label}</span>`;
    container.appendChild(row);
  }
}

function setSaveMsg(text, ok=true) {
  const el = $("saveMsg");
  el.textContent = text;
  el.classList.toggle("ok", !!ok);
  el.classList.toggle("bad", !ok);
}

async function loadEditorFromSprint(sprint) {
  const meta = (sprint && sprint.meta) ? sprint.meta : {};
  $("brief").value = (meta.brief || "").toString();
  $("gateProfile").value = (meta.gate_profile || "quick").toString();

  const am = meta.enable_auto_merge;
  $("autoMergeOverride").value = (am === true) ? "on" : (am === false) ? "off" : "inherit";
  const ap = meta.automation_paused;
  $("pauseOverride").value = (ap === true) ? "on" : (ap === false) ? "off" : "inherit";

  const active = Array.isArray(meta.active_agents) ? meta.active_agents : [];
  const checks = document.querySelectorAll("#agents input[type=checkbox]");
  for (const c of checks) {
    const aid = c.getAttribute("data-agent");
    c.checked = active.includes(aid);
  }
}

async function saveSprintMeta() {
  const sid = $("sprintSelect").value;
  if (!sid) return;

  const checks = document.querySelectorAll("#agents input[type=checkbox]");
  const active_agents = [];
  for (const c of checks) {
    if (c.checked) active_agents.push(c.getAttribute("data-agent"));
  }

  const autoMergeOverride = $("autoMergeOverride").value;
  const pauseOverride = $("pauseOverride").value;

  const meta = {
    brief: $("brief").value,
    active_agents,
    // used by orchestrator prompts (for now)
    required_acks_by_round: {
      "R1_CONTRACTS": active_agents,
    },
    gate_profile: $("gateProfile").value,
    enable_auto_merge: autoMergeOverride === "inherit" ? null : (autoMergeOverride === "on"),
    automation_paused: pauseOverride === "inherit" ? null : (pauseOverride === "on"),
  };
  // Strip nulls so we truly "inherit"
  for (const k of Object.keys(meta)) {
    if (meta[k] === null) delete meta[k];
  }

  await apiFetch(`/api/sprints/${encodeURIComponent(sid)}`, { method: "POST", body: JSON.stringify({ meta }) });
  setSaveMsg("Saved", true);
  await loadSprintDetail();
}

async function pollEvents() {
  const sid = $("sprintSelect").value;
  const tail = parseInt($("tail").value || "150", 10);
  const q = new URLSearchParams();
  q.set("tail", String(tail));
  if (sid) q.set("sprint_id", sid);
  const ev = await apiFetch(`/api/events?${q.toString()}`);
  $("events").textContent = pretty(ev);
}

async function fetchArtifact() {
  const sid = $("sprintSelect").value;
  const p = $("artifactPath").value.trim();
  if (!sid || !p) return;
  const url = `/api/artifacts/${encodeURIComponent(sid)}/${p.replaceAll("..", "")}`;
  const res = await fetch(url, { headers: { "X-Studio-Gateway-Token": getToken() } });
  const text = await res.text();
  $("artifact").textContent = text;
}

async function openConfig() {
  const cfg = await apiFetch("/api/config");
  $("cfgBindHost").value = cfg.bind_host || "127.0.0.1";
  $("cfgPort").value = cfg.port || 18790;
  $("cfgMaxConc").value = cfg.max_concurrent_global || 4;
  $("cfgAutoMerge").checked = !!cfg.enable_auto_merge;
  $("cfgPaused").checked = !!cfg.automation_paused;
  $("configDialog").showModal();
}

async function saveConfig() {
  const patch = {
    bind_host: $("cfgBindHost").value.trim(),
    port: parseInt($("cfgPort").value || "18790", 10),
    max_concurrent_global: parseInt($("cfgMaxConc").value || "4", 10),
    enable_auto_merge: !!$("cfgAutoMerge").checked,
    automation_paused: !!$("cfgPaused").checked,
  };
  await apiFetch("/api/config", { method: "POST", body: JSON.stringify(patch) });
  $("configDialog").close();
  await refreshStatus();
}

saveTokenBtn.addEventListener("click", () => {
  setToken(tokenInput.value.trim());
});

$("refresh").addEventListener("click", async () => {
  await refreshHealth();
  await refreshStatus();
});
$("sprintSelect").addEventListener("change", async () => {
  await loadSprintDetail();
  await pollEvents();
});
$("pollEvents").addEventListener("click", pollEvents);
$("saveBrief").addEventListener("click", async () => {
  try {
    setSaveMsg("Saving…", true);
    await saveSprintMeta();
  } catch (e) {
    setSaveMsg(`Save failed: ${e.message}`, false);
  }
});
$("fetchArtifact").addEventListener("click", fetchArtifact);
$("openConfig").addEventListener("click", openConfig);
$("saveConfig").addEventListener("click", saveConfig);
$("autoPoll").addEventListener("change", async () => {
  if ($("autoPoll").checked) {
    if (autoPollTimer) clearInterval(autoPollTimer);
    autoPollTimer = setInterval(() => { pollEvents().catch(() => {}); }, 2000);
  } else {
    if (autoPollTimer) clearInterval(autoPollTimer);
    autoPollTimer = null;
  }
});

$("createSprint").addEventListener("click", async () => {
  const sprint_id = $("newSprintId").value.trim();
  const title = $("newSprintTitle").value.trim() || sprint_id;
  if (!sprint_id) return;
  await apiFetch("/api/sprints", { method: "POST", body: JSON.stringify({ sprint_id, title }) });
  $("newSprintId").value = "";
  $("newSprintTitle").value = "";
  await refreshStatus();
});

$("runSprint").addEventListener("click", async () => {
  const sid = $("sprintSelect").value;
  if (!sid) return;
  await apiFetch(`/api/sprints/${encodeURIComponent(sid)}/run`, { method: "POST", body: "{}" });
  await refreshStatus();
});

$("stepSprint").addEventListener("click", async () => {
  const sid = $("sprintSelect").value;
  if (!sid) return;
  await apiFetch(`/api/sprints/${encodeURIComponent(sid)}/step`, { method: "POST", body: "{}" });
  await refreshStatus();
});

$("cancelSprint").addEventListener("click", async () => {
  const sid = $("sprintSelect").value;
  if (!sid) return;
  await apiFetch(`/api/sprints/${encodeURIComponent(sid)}/cancel`, { method: "POST", body: "{}" });
  await refreshStatus();
});

// boot
tokenInput.value = getToken();
loadAgents().then(() => refreshHealth().then(refreshStatus).then(pollEvents));

