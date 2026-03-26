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
};

let currentUser = null;

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
    throw new Error("Enter a mock token, e.g. mock:student@campusa.edu");
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
        ws.close();
        resolve();
      } else if (msg.type === "error") {
        setStatus("error", msg.message || "Streaming error");
        ws.close();
        reject(new Error(msg.message || "Streaming error"));
      }
    };

    ws.onerror = () => {
      setStatus("error", "WebSocket connection error");
      reject(new Error("WebSocket error"));
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

function init() {
  loadSavedToken();
  bindQuickLoginButtons();

  bind("btnHealth", checkHealth);
  bind("btnLogin", handleLogin);
  bind("btnRefresh", handleRefresh);
  bind("btnLogout", handleLogout);
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

  document.getElementById("btnClearToken").addEventListener("click", () => {
    saveToken("");
    currentUser = null;
    els.authInfo.textContent = "Token cleared";
    setStatus("idle", "Idle");
  });

  setStatus("idle", "Ready");
}

init();
