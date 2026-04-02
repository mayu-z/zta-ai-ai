/*
  Minimal frontend for ZTA-AI backend.
  - Handles auth token lifecycle
  - Calls REST endpoints using fetch
  - Opens chat WebSocket stream
  - Renders response JSON and basic tables/cards
*/

const els = {
  apiBase: document.getElementById("apiBase"),
  googleToken: document.getElementById("googleToken"),
  bearerToken: document.getElementById("bearerToken"),
  authInfo: document.getElementById("authInfo"),
  healthStatus: document.getElementById("healthStatus"),
  statusBar: document.getElementById("statusBar"),
  output: document.getElementById("output"),
  dashboardCards: document.getElementById("dashboardCards"),
  chatQuery: document.getElementById("chatQuery"),
  chatStream: document.getElementById("chatStream"),
  usersTableWrap: document.getElementById("usersTableWrap"),
  loginDropdown: document.getElementById("loginDropdown"),
  btnLoginMenu: document.getElementById("btnLoginMenu"),
  btnLogout: document.getElementById("btnLogout"),
  btnClearToken: document.getElementById("btnClearToken"),
};

let currentUser = null;

// ============================================================================
// LOGIN DROPDOWN & LOGOUT FUNCTIONALITY
// ============================================================================

function toggleLoginDropdown(e) {
  e.stopPropagation();
  if (els.loginDropdown.classList.contains("show")) {
    els.loginDropdown.classList.remove("show");
  } else {
    els.loginDropdown.classList.add("show");
  }
}

function closeLoginDropdown() {
  els.loginDropdown.classList.remove("show");
}

function handleLoginDropdownItem(email) {
  els.googleToken.value = `mock:${email}`;
  closeLoginDropdown();
  // Auto-trigger login
  handleLogin().catch((err) => {
    setStatus("error", err.message || String(err));
  });
}

// Update handleLogout to also close dropdown and clear local data
async function handleLogoutHeader() {
  try {
    await callApi("/auth/logout", { method: "POST" });
  } catch (err) {
    // Logout API might fail if token invalid, but we should still clear locally
    console.warn("Logout API call failed:", err);
  }
  saveToken("");
  currentUser = null;
  els.authInfo.textContent = "Logged out";
  closeLoginDropdown();
  setStatus("ok", "Logged out");
}

// Event listeners for login dropdown
els.btnLoginMenu.addEventListener("click", toggleLoginDropdown);

document.addEventListener("click", (e) => {
  if (!e.target.closest(".login-dropdown-wrapper")) {
    closeLoginDropdown();
  }
});

document.querySelectorAll(".dropdown-item").forEach((item) => {
  item.addEventListener("click", function () {
    const email = this.getAttribute("data-email");
    handleLoginDropdownItem(email);
  });
});

els.btnLogout.addEventListener("click", handleLogoutHeader);

// ============================================================================
// EXISTING FUNCTIONALITY (PRESERVED)
// ============================================================================

function baseUrl() {
  return els.apiBase.value.trim().replace(/\/$/, "") || "http://localhost:8000";
}

function setStatus(type, text) {
  els.statusBar.className = `status ${type}`;
  els.statusBar.textContent = text;
}

function printOutput(data) {
  if (typeof data === "string") {
    els.output.textContent = data;
    return;
  }
  els.output.textContent = JSON.stringify(data, null, 2);
}

function getToken() {
  return els.bearerToken.value.trim();
}

function saveToken(token) {
  els.bearerToken.value = token || "";
  localStorage.setItem("zta_token", token || "");
}

function loadSavedToken() {
  const token = localStorage.getItem("zta_token") || "";
  els.bearerToken.value = token;
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function callApi(path, options = {}) {
  const url = `${baseUrl()}${path}`;
  const merged = {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  };

  if (options.body !== undefined) {
    merged.body = typeof options.body === "string" ? options.body : JSON.stringify(options.body);
  }

  setStatus("loading", `${merged.method} ${path}...`);
  const res = await fetch(url, merged);

  let payload;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await res.json();
  } else {
    payload = await res.text();
  }

  if (!res.ok) {
    setStatus("error", `${res.status} ${res.statusText}`);
    printOutput(payload);
    throw new Error((payload && payload.error) || `Request failed: ${res.status}`);
  }

  setStatus("ok", `${res.status} ${res.statusText}`);
  printOutput(payload);
  return payload;
}

function renderCards(items) {
  els.dashboardCards.innerHTML = "";
  items.forEach((item) => {
    const div = document.createElement("div");
    div.className = "kpi";
    div.innerHTML = `<strong>${item.title}</strong><div>${item.value}</div>`;
    els.dashboardCards.appendChild(div);
  });
}

function renderTable(container, rows) {
  if (!rows || !rows.length) {
    container.innerHTML = "<p class='muted'>No data</p>";
    return;
  }

  const cols = Object.keys(rows[0]);
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");

  cols.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    trh.appendChild(th);
  });
  thead.appendChild(trh);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    cols.forEach((c) => {
      const td = document.createElement("td");
      const val = row[c];
      td.textContent = typeof val === "object" && val !== null ? JSON.stringify(val) : String(val ?? "");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  container.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  wrap.appendChild(table);
  container.appendChild(wrap);
}

async function loginWithToken(mockToken) {
  const payload = await callApi("/auth/google", {
    method: "POST",
    body: { google_token: mockToken },
  });

  saveToken(payload.jwt);
  currentUser = payload.user;
  els.authInfo.textContent = `Logged in as ${payload.user.email} (${payload.user.persona})`;
}

async function handleLogin() {
  const raw = els.googleToken.value.trim();
  if (!raw) {
    throw new Error("Enter a mock token, e.g. mock:executive@ipeds.local");
  }
  await loginWithToken(raw);
}

async function handleRefresh() {
  const token = getToken();
  if (!token) {
    throw new Error("No token to refresh");
  }

  const payload = await callApi("/auth/refresh", {
    method: "POST",
    body: { jwt: token },
  });

  saveToken(payload.jwt);
}

async function handleLogout() {
  await callApi("/auth/logout", { method: "POST" });
  saveToken("");
  currentUser = null;
  els.authInfo.textContent = "Logged out";
}

async function checkHealth() {
  const payload = await callApi("/health");
  els.healthStatus.textContent = `Health: ${payload.status} (${payload.service})`;
}

async function getSuggestions() {
  const payload = await callApi("/chat/suggestions");
  renderCards(payload.map((x) => ({ title: x.id, value: x.text })));
}

async function getHistory() {
  const payload = await callApi("/chat/history");
  renderTable(els.usersTableWrap, payload);
}

/*
  WebSocket chat streaming call:
  - Connects to /chat/stream?token=<jwt>
  - Sends {query}
  - Appends token frames until done/error
*/
function streamChat() {
  return new Promise((resolve, reject) => {
    const token = getToken();
    const query = els.chatQuery.value.trim();
    if (!token) return reject(new Error("Login first"));
    if (!query) return reject(new Error("Enter a chat query"));

    const wsBase = baseUrl().replace(/^http/, "ws");
    const ws = new WebSocket(`${wsBase}/chat/stream?token=${encodeURIComponent(token)}`);
    let settled = false;

    els.chatStream.textContent = "";
    setStatus("loading", "Streaming chat response...");

    ws.onopen = () => {
      ws.send(JSON.stringify({ query }));
    };

    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === "token") {
        els.chatStream.textContent += msg.content || "";
      } else if (msg.type === "done") {
        els.chatStream.textContent += `\n\n[source=${msg.source}] [latency_ms=${msg.latency_ms}]`;
        setStatus("ok", "Streaming complete");
        settled = true;
        ws.close();
        resolve();
      } else if (msg.type === "error") {
        setStatus("error", msg.message || "Streaming error");
        settled = true;
        ws.close();
        reject(new Error(msg.message || "Streaming error"));
      }
    };

    ws.onerror = () => {
      setStatus("error", "WebSocket connection error");
      settled = true;
      reject(new Error("WebSocket error"));
    };

    ws.onclose = () => {
      if (settled) return;
      setStatus("error", "Chat stream closed. Login again if your token expired.");
      reject(new Error("WebSocket closed before the response completed"));
    };
  });
}

async function getUsers() {
  const page = document.getElementById("usersPage").value;
  const limit = document.getElementById("usersLimit").value;
  const search = document.getElementById("usersSearch").value.trim();

  const qp = new URLSearchParams({ page, limit });
  if (search) qp.set("search", search);

  const payload = await callApi(`/admin/users?${qp.toString()}`);
  renderTable(els.usersTableWrap, payload.items || []);
}

async function updateUser() {
  const userId = document.getElementById("updUserId").value.trim();
  if (!userId) throw new Error("user_id is required");

  const body = {};
  const persona = document.getElementById("updPersona").value.trim();
  const dept = document.getElementById("updDept").value.trim();
  const status = document.getElementById("updStatus").value.trim();
  if (persona) body.persona_type = persona;
  if (dept) body.department = dept;
  if (status) body.status = status;

  await callApi(`/admin/users/${encodeURIComponent(userId)}`, { method: "PUT", body });
}

async function importUsers() {
  const file = document.getElementById("importFile").files[0];
  if (!file) throw new Error("Select a CSV file");

  const fd = new FormData();
  fd.append("file", file);

  setStatus("loading", "Uploading CSV...");
  const res = await fetch(`${baseUrl()}/admin/users/import`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: fd,
  });
  const payload = await res.json();

  if (!res.ok) {
    setStatus("error", `${res.status} ${res.statusText}`);
    printOutput(payload);
    throw new Error(payload.error || "Import failed");
  }

  setStatus("ok", "Import completed");
  printOutput(payload);
}

async function listSources() {
  await callApi("/admin/data-sources");
}

async function getSchema() {
  const id = document.getElementById("schemaSourceId").value.trim();
  if (!id) throw new Error("source_id is required");
  await callApi(`/admin/data-sources/${encodeURIComponent(id)}/schema`);
}

async function createSource() {
  const name = document.getElementById("srcName").value.trim();
  const sourceType = document.getElementById("srcType").value.trim();
  const deptScope = document.getElementById("srcDeptScope").value.trim();
  const configRaw = document.getElementById("srcConfig").value.trim();

  if (!name || !sourceType) throw new Error("name and source_type are required");

  let config = {};
  if (configRaw) config = JSON.parse(configRaw);

  await callApi("/admin/data-sources", {
    method: "POST",
    body: {
      name,
      source_type: sourceType,
      department_scope: deptScope ? deptScope.split(",").map((x) => x.trim()).filter(Boolean) : [],
      config,
    },
  });
}

async function getAudit() {
  const page = document.getElementById("auditPage").value;
  const limit = document.getElementById("auditLimit").value;
  const blockedOnly = document.getElementById("auditBlockedOnly").checked;

  const qp = new URLSearchParams({ page, limit, blocked_only: String(blockedOnly) });
  await callApi(`/admin/audit-log?${qp.toString()}`);
}

async function killSwitch() {
  const scope = document.getElementById("killScope").value.trim();
  const target = document.getElementById("killTarget").value.trim();
  if (!scope) throw new Error("scope is required");

  await callApi("/admin/security/kill", {
    method: "POST",
    body: { scope, target_id: target || null },
  });
}

function bind(id, fn) {
  const el = document.getElementById(id);
  el.addEventListener("click", async () => {
    try {
      await fn();
    } catch (err) {
      setStatus("error", err.message || String(err));
    }
  });
}

function bindQuickLoginButtons() {
  document.querySelectorAll(".quick-login").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const email = btn.getAttribute("data-email");
        await loginWithToken(`mock:${email}`);
      } catch (err) {
        setStatus("error", err.message || String(err));
      }
    });
  });
}

// ==================== Pipeline Monitor ====================

const pipelineMonitor = {
  ws: null,
  activePipelines: new Map(),
  selectedPipelineId: null,
  // Stages must match backend pipeline.py exactly
  stages: [
    { index: 0, name: "history_user_message", label: "Store User Message" },
    { index: 1, name: "interpreter", label: "Interpreter (Sanitizer → Domain Gate → Intent)" },
    { index: 2, name: "intent_cache", label: "Intent Cache Check" },
    { index: 3, name: "slm_render", label: "SLM Template Render" },
    { index: 4, name: "output_guard", label: "Output Guard Validation" },
    { index: 5, name: "compiler", label: "Query Plan Compiler" },
    { index: 6, name: "policy_authorization", label: "Policy Authorization" },
    { index: 7, name: "tool_execution", label: "Tool Layer Execution" },
    { index: 8, name: "field_masking", label: "Field Masking" },
    { index: 9, name: "detokenization", label: "Detokenization" },
    { index: 10, name: "cache_storage", label: "Cache Storage" },
    { index: 11, name: "history_assistant_message", label: "Store Assistant Message" },
    { index: 12, name: "audit_logging", label: "Audit Logging" }
  ]
};

function initializePipelineStages() {
  const container = document.getElementById('pipelineStages');
  if (!container) return;

  container.innerHTML = '';
  pipelineMonitor.stages.forEach(stage => {
    const stageCard = document.createElement('div');
    stageCard.className = 'stage-card pending';
    stageCard.id = `stage-${stage.index}`;
    stageCard.innerHTML = `
      <div class="stage-info">
        <div class="stage-name">${stage.label}</div>
        <div class="stage-meta" id="stage-meta-${stage.index}">Waiting...</div>
      </div>
      <div class="stage-timing" id="stage-timing-${stage.index}">--</div>
    `;
    container.appendChild(stageCard);
  });
}

function connectPipelineMonitor() {
  const token = getToken();
  if (!token) {
    setStatus('error', 'Please login first to view the pipeline monitor');
    return;
  }

  const wsBase = baseUrl().replace(/^http/, 'ws');
  const ws = new WebSocket(`${wsBase}/admin/pipeline/monitor?token=${encodeURIComponent(token)}`);

  ws.onopen = () => {
    pipelineMonitor.ws = ws;
    document.getElementById('btnConnectMonitor').disabled = true;
    document.getElementById('btnDisconnectMonitor').disabled = false;
    document.getElementById('monitorStatus').className = 'status ok';
    document.getElementById('monitorStatus').textContent = 'Connected';
    initializePipelineStages();
    setStatus('ok', 'Pipeline monitor connected');
  };

  ws.onmessage = (evt) => {
    const message = JSON.parse(evt.data);
    handlePipelineEvent(message);
  };

  ws.onerror = () => {
    document.getElementById('monitorStatus').className = 'status error';
    document.getElementById('monitorStatus').textContent = 'Connection Error';
    setStatus('error', 'Pipeline monitor connection error');
  };

  ws.onclose = () => {
    pipelineMonitor.ws = null;
    document.getElementById('btnConnectMonitor').disabled = false;
    document.getElementById('btnDisconnectMonitor').disabled = true;
    document.getElementById('monitorStatus').className = 'status idle';
    document.getElementById('monitorStatus').textContent = 'Disconnected';
    setStatus('idle', 'Pipeline monitor disconnected');
  };
}

function disconnectPipelineMonitor() {
  if (pipelineMonitor.ws) {
    pipelineMonitor.ws.close();
  }
}

function handlePipelineEvent(message) {
  const { type, data } = message;

  switch (type) {
    case 'connected':
      console.log('Pipeline monitor connected');
      break;

    case 'pipeline_start':
      handlePipelineStart(data);
      break;

    case 'stage_event':
      handleStageEvent(data);
      break;

    case 'pipeline_complete':
      handlePipelineComplete(data);
      break;

    case 'error':
      console.error('Pipeline monitor error:', message);
      setStatus('error', data.message || 'Monitor error');
      break;
  }
}

function handlePipelineStart(data) {
  const { pipeline_id, query_text, user_id } = data;

  pipelineMonitor.activePipelines.set(pipeline_id, {
    id: pipeline_id,
    query: query_text,
    user: user_id,
    stages: new Map(),
    startedAt: new Date(data.started_at),
    status: 'running'
  });

  // Auto-select first pipeline
  if (!pipelineMonitor.selectedPipelineId) {
    pipelineMonitor.selectedPipelineId = pipeline_id;
  }

  updateActivePipelinesList();

  // Reset stage display if this is the selected pipeline
  if (pipelineMonitor.selectedPipelineId === pipeline_id) {
    resetStageDisplay();
  }
}

function handleStageEvent(data) {
  const { pipeline_id, stage_name, stage_index, status, duration_ms, error_message } = data;

  const pipeline = pipelineMonitor.activePipelines.get(pipeline_id);
  if (!pipeline) return;

  pipeline.stages.set(stage_index, {
    name: stage_name,
    status,
    duration_ms,
    error_message
  });

  // Update visualization if this is the selected pipeline
  if (pipelineMonitor.selectedPipelineId === pipeline_id) {
    updateStageCard(stage_index, status, duration_ms, error_message);
  }
}

function handlePipelineComplete(data) {
  const { pipeline_id, status, total_duration_ms, final_message } = data;

  const pipeline = pipelineMonitor.activePipelines.get(pipeline_id);
  if (pipeline) {
    pipeline.status = status;
    pipeline.totalDuration = total_duration_ms;
    pipeline.finalMessage = final_message;
    updateActivePipelinesList();
  }
}

function updateStageCard(stageIndex, status, durationMs, errorMessage) {
  const card = document.getElementById(`stage-${stageIndex}`);
  const meta = document.getElementById(`stage-meta-${stageIndex}`);
  const timing = document.getElementById(`stage-timing-${stageIndex}`);

  if (!card) return;

  // Update status class
  card.className = `stage-card ${status}`;

  // Update metadata
  if (status === 'started') {
    meta.textContent = 'Running...';
    timing.textContent = '⏱️';
  } else if (status === 'completed') {
    meta.textContent = 'Completed';
    timing.textContent = `${durationMs}ms`;
  } else if (status === 'error') {
    meta.textContent = errorMessage || 'Error occurred';
    timing.textContent = `${durationMs}ms`;
  } else if (status === 'skipped') {
    meta.textContent = 'Skipped';
    timing.textContent = '--';
  }
}

function resetStageDisplay() {
  pipelineMonitor.stages.forEach(stage => {
    const card = document.getElementById(`stage-${stage.index}`);
    const meta = document.getElementById(`stage-meta-${stage.index}`);
    const timing = document.getElementById(`stage-timing-${stage.index}`);

    if (card) card.className = 'stage-card pending';
    if (meta) meta.textContent = 'Waiting...';
    if (timing) timing.textContent = '--';
  });
}

function updateActivePipelinesList() {
  const container = document.getElementById('activePipelines');
  if (!container) return;

  container.innerHTML = '';

  // Show most recent first
  const pipelines = Array.from(pipelineMonitor.activePipelines.values())
    .sort((a, b) => b.startedAt - a.startedAt)
    .slice(0, 20); // Show last 20

  if (pipelines.length === 0) {
    container.innerHTML = '<p class="muted">No active pipelines</p>';
    return;
  }

  pipelines.forEach(pipeline => {
    const item = document.createElement('div');
    item.className = 'pipeline-item';
    if (pipeline.id === pipelineMonitor.selectedPipelineId) {
      item.classList.add('selected');
    }

    const statusIcon = pipeline.status === 'running' ? '🔄' :
                      pipeline.status === 'success' ? '✅' : '❌';

    item.innerHTML = `
      <div class="pipeline-query">${statusIcon} ${pipeline.query.substring(0, 40)}${pipeline.query.length > 40 ? '...' : ''}</div>
      <div class="pipeline-details">
        ${pipeline.user} • ${pipeline.startedAt.toLocaleTimeString()}
        ${pipeline.totalDuration ? ` • ${pipeline.totalDuration}ms` : ''}
      </div>
    `;

    item.addEventListener('click', () => {
      pipelineMonitor.selectedPipelineId = pipeline.id;
      updateActivePipelinesList();
      renderSelectedPipeline(pipeline);
    });

    container.appendChild(item);
  });
}

function renderSelectedPipeline(pipeline) {
  resetStageDisplay();

  pipeline.stages.forEach((stageData, stageIndex) => {
    updateStageCard(
      stageIndex,
      stageData.status,
      stageData.duration_ms,
      stageData.error_message
    );
  });
}

function initPipelineMonitor() {
  bind('btnConnectMonitor', connectPipelineMonitor);
  bind('btnDisconnectMonitor', disconnectPipelineMonitor);
  initializePipelineStages();
}

function init() {
  loadSavedToken();
  // bindQuickLoginButtons() removed - now using header dropdown

  bind("btnHealth", checkHealth);
  bind("btnLogin", handleLogin);
  bind("btnRefresh", handleRefresh);
  bind("btnSuggestions", getSuggestions);
  bind("btnHistory", getHistory);
  bind("btnStreamChat", streamChat);

  bind("btnGetUsers", getUsers);
  bind("btnUpdateUser", updateUser);
  bind("btnImportUsers", importUsers);
  bind("btnListSources", listSources);
  bind("btnGetSchema", getSchema);
  bind("btnCreateSource", createSource);
  bind("btnAudit", getAudit);
  bind("btnKill", killSwitch);

  // Legacy button handler for token clearing
  const btnClearToken = document.getElementById("btnClearToken");
  if (btnClearToken) {
    btnClearToken.addEventListener("click", () => {
      saveToken("");
      currentUser = null;
      els.authInfo.textContent = "Token cleared";
      setStatus("idle", "Idle");
    });
  }

  // Initialize pipeline monitor
  initPipelineMonitor();

  setStatus("idle", "Ready");
}

init();
