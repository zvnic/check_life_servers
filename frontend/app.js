const state = {
  servers: [],
  selected: null,
  currentView: "overview",
  currentUser: null,
  version: null,
};
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  if (response.status === 401) {
    $("#login-screen").classList.remove("hidden");
    throw new Error("unauthorized");
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}

function text(selector, value) {
  $(selector).textContent = value ?? "—";
}

function formatTime(value) {
  if (!value) return "никогда";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = value ?? "";
  return node.innerHTML;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 1800);
}

async function loadVersion() {
  try {
    const info = await api("/api/v1/system/version");
    state.version = info.version;
    document.querySelectorAll(".service-version").forEach((node) => {
      node.textContent = `v${info.version}`;
    });
  } catch {
    document.querySelectorAll(".service-version").forEach((node) => {
      node.textContent = "недоступна";
    });
  }
}

function renderSummary(summary) {
  text("#uptime", summary.uptime_percent);
  text("#total", summary.total);
  text("#online", summary.online);
  text("#offline", summary.offline);
  text("#unknown", summary.unknown);
  text("#donut-total", summary.total);
  text("#leg-online", summary.online);
  text("#leg-offline", summary.offline);
  text("#leg-unknown", summary.unknown);
  text("#monitor-time", `обновлено ${formatTime(summary.generated_at)}`);
  const total = summary.total || 1;
  const online = summary.online / total * 360;
  const offline = online + summary.offline / total * 360;
  $("#donut").style.setProperty("--online", `${online}deg`);
  $("#donut").style.setProperty("--offline", `${offline}deg`);
}

function visibleServers() {
  const query = $("#search").value.toLowerCase();
  return state.servers.filter((server) => {
    const matchesSearch = server.name.toLowerCase().includes(query);
    const matchesView = state.currentView !== "incidents" || server.status === "offline";
    return matchesSearch && matchesView;
  });
}

function renderServers() {
  const rows = visibleServers();
  $("#server-table").innerHTML = rows.map((server) => `
    <tr data-id="${server.id}">
      <td class="server-name">${escapeHtml(server.name)}</td>
      <td>${escapeHtml(server.platform)}</td>
      <td><span class="status ${server.status}">
        <i class="dot ${server.status === "online" ? "green" : server.status === "offline" ? "red" : "gray"}"></i>
        ${server.status}
      </span></td>
      <td>${formatTime(server.last_seen_at)}</td>
      <td>${server.heartbeat_count}</td>
    </tr>
  `).join("");
  $("#empty").classList.toggle("visible", state.servers.length === 0);
  document.querySelectorAll("[data-id]").forEach((row) => {
    row.onclick = () => loadHeartbeats(row.dataset.id);
  });
}

function renderIncidents() {
  const incidents = state.servers.filter((server) => server.status === "offline");
  text("#incident-count", `${incidents.length} активных`);
  $("#incident-list").innerHTML = incidents.map((server) => `
    <article class="incident">
      <i></i>
      <div><b>${escapeHtml(server.name)}</b><small>${escapeHtml(server.platform)} · heartbeat не поступает</small></div>
      <time>${formatTime(server.last_seen_at)}</time>
    </article>
  `).join("");
  $("#no-incidents").classList.toggle("visible", incidents.length === 0);
}

function drawChart(events) {
  const chart = $("#chart");
  if (!events.length) {
    chart.classList.add("empty");
    return;
  }
  chart.classList.remove("empty");
  const values = [...events].reverse().map((event) => Math.min(event.latency_ms, 30000));
  const max = Math.max(...values, 1000);
  const points = values.map((value, index) => [
    values.length === 1 ? 450 : index / (values.length - 1) * 900,
    220 - value / max * 190,
  ]);
  const line = points.map(
    ([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`
  ).join(" ");
  $(".line").setAttribute("d", line);
  $(".area").setAttribute("d", `${line} L900,240 L0,240 Z`);
}

async function loadHeartbeats(id) {
  state.selected = id;
  drawChart(await api(`/api/v1/servers/${id}/heartbeats`));
  if (state.currentView === "objects") switchView("analytics");
}

const viewMeta = {
  overview: ["ЦЕНТР УПРАВЛЕНИЯ", "Состояние инфраструктуры"],
  objects: ["ИНФРАСТРУКТУРА", "Контролируемые объекты"],
  incidents: ["СОБЫТИЯ", "Инциденты и недоступность"],
  analytics: ["МЕТРИКИ", "Аналитика доступности"],
  settings: ["УПРАВЛЕНИЕ", "Настройки системы"],
};

function switchView(view) {
  state.currentView = view;
  const visible = {
    metrics: view === "overview" || view === "analytics",
    analytics: view === "overview" || view === "analytics",
    objects: view === "overview" || view === "objects",
    incidents: view === "incidents",
    settings: view === "settings",
  };
  $("#metrics-section").classList.toggle("hidden-section", !visible.metrics);
  $("#analytics-section").classList.toggle("hidden-section", !visible.analytics);
  $("#objects-section").classList.toggle("hidden-section", !visible.objects);
  $("#incidents-section").classList.toggle("hidden-section", !visible.incidents);
  $("#settings-section").classList.toggle("hidden-section", !visible.settings);
  document.querySelectorAll("nav [data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  text("#page-eyebrow", viewMeta[view][0]);
  text("#page-title", viewMeta[view][1]);
  renderServers();
  renderIncidents();
  window.history.replaceState(null, "", `#${view}`);
}

async function checkSystem() {
  const status = $("#settings-api-status");
  status.textContent = "проверка…";
  status.className = "";
  try {
    const ready = await api("/api/v1/health/ready");
    status.textContent = ready.status === "ready" ? "доступен" : "деградация";
    status.className = ready.status === "ready" ? "ok" : "error-state";
    await loadVersion();
    showToast("Система проверена");
  } catch {
    status.textContent = "недоступен";
    status.className = "error-state";
  }
}

async function loadDashboard() {
  const [me, summary, servers] = await Promise.all([
    api("/api/v1/auth/me"),
    api("/api/v1/dashboard/summary"),
    api("/api/v1/servers"),
  ]);
  $("#login-screen").classList.add("hidden");
  state.currentUser = me;
  state.servers = servers;
  text("#current-user", me.login);
  text("#settings-user", me.login);
  text("#settings-role", me.role);
  renderSummary(summary);
  renderServers();
  renderIncidents();
  if (state.selected) await loadHeartbeats(state.selected);
}

document.querySelectorAll("nav [data-view]").forEach((button) => {
  button.onclick = () => switchView(button.dataset.view);
});
document.querySelectorAll("[data-copy]").forEach((button) => {
  button.onclick = async () => {
    await navigator.clipboard.writeText($(button.dataset.copy).textContent);
    showToast("Команда скопирована");
  };
});

$("#add-device").onclick = () => {
  $("#device-modal").classList.remove("hidden");
  $("#device-error").textContent = "";
};
$("#close-device-modal").onclick = () => $("#device-modal").classList.add("hidden");
$("#device-modal").onclick = (event) => {
  if (event.target === $("#device-modal")) $("#device-modal").classList.add("hidden");
};
$("#device-form").onsubmit = async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  $("#device-error").textContent = "";
  $("#generated-command").classList.add("hidden");
  try {
    const bootstrap = await api("/api/v1/enrollment-tokens", {
      method: "POST",
      body: JSON.stringify({
        server_name: form.get("server_name"),
        platform: form.get("platform"),
      }),
    });
    text("#install-command", bootstrap.command);
    text("#command-expiry", formatTime(bootstrap.expires_at));
    $("#generated-command").classList.remove("hidden");
    $("#bootstrap-warning").textContent = bootstrap.command.includes("localhost")
      ? "Внимание: CLS_PUBLIC_URL указывает на localhost. Перед установкой на внешнее устройство настройте публичный HTTPS-домен."
      : "Команда содержит одноразовый код. Не публикуйте и не пересылайте её посторонним.";
  } catch (error) {
    $("#device-error").textContent = error.message === "unauthorized"
      ? "Сессия завершена — войдите снова."
      : "Не удалось создать установочную команду.";
  }
};

$("#login-form").onsubmit = async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  $("#login-error").textContent = "";
  try {
    await api("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({login: form.get("login"), password: form.get("password")}),
    });
    await loadDashboard();
  } catch {
    $("#login-error").textContent = "Неверный логин или пароль";
  }
};
$("#logout").onclick = async () => {
  await api("/api/v1/auth/logout", {method: "POST"});
  $("#login-screen").classList.remove("hidden");
};
$("#refresh").onclick = async () => {
  await loadDashboard();
  showToast("Данные обновлены");
};
$("#check-system").onclick = checkSystem;
$("#search").oninput = renderServers;

const initialView = window.location.hash.slice(1);
switchView(viewMeta[initialView] ? initialView : "overview");
loadVersion();
loadDashboard().catch(() => {});
window.setInterval(() => loadDashboard().catch(() => {}), 30000);
