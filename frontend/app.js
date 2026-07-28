const state = {
  servers: [], availability: null, selected: null, currentView: "overview",
  currentUser: null, version: null, hours: 24,
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
function text(selector, value) { $(selector).textContent = value ?? "—"; }
function escapeHtml(value) {
  const node = document.createElement("span"); node.textContent = value ?? ""; return node.innerHTML;
}
function formatTime(value) {
  if (!value) return "никогда";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(new Date(value));
}
function duration(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds} сек`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} мин`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(seconds < 36000 ? 1 : 0)} ч`;
  return `${(seconds / 86400).toFixed(1)} д`;
}
function bytes(value) {
  if (value == null) return "—";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]; let i = 0; let n = Number(value);
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}
function showToast(message) {
  const toast = $("#toast"); toast.textContent = message; toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 1800);
}
function availabilityFor(id) {
  return state.availability?.servers.find((item) => item.server_id === id);
}

async function loadVersion() {
  try {
    const info = await api("/api/v1/system/version"); state.version = info.version;
    document.querySelectorAll(".service-version").forEach((node) => node.textContent = `v${info.version}`);
  } catch {
    document.querySelectorAll(".service-version").forEach((node) => node.textContent = "недоступна");
  }
}
function renderSummary(summary) {
  text("#uptime", state.availability?.uptime_percent?.toFixed(2));
  text("#total", summary.total); text("#online", summary.online);
  text("#offline", summary.offline); text("#unknown", summary.unknown);
  text("#uptime-caption", `за ${state.hours === 24 ? "последние 24 часа" : state.hours === 168 ? "7 дней" : "30 дней"}`);
  text("#monitor-time", `обновлено ${formatTime(summary.generated_at)}`);
}
function visibleServers() {
  const query = $("#search").value.toLowerCase();
  return state.servers.filter((server) => server.name.toLowerCase().includes(query));
}
function renderServers() {
  $("#server-table").innerHTML = visibleServers().map((server) => {
    const history = availabilityFor(server.id);
    return `<tr data-id="${server.id}">
      <td class="server-name">${escapeHtml(server.name)}</td><td>${escapeHtml(server.platform)}</td>
      <td><span class="status ${server.status}"><i class="dot ${server.status === "online" ? "green" : server.status === "offline" ? "red" : "gray"}"></i>${server.status}</span></td>
      <td class="uptime-cell">${history?.uptime_percent == null ? "—" : `${history.uptime_percent.toFixed(2)}%`}</td>
      <td>${duration(history?.downtime_seconds)}</td><td>${formatTime(server.last_seen_at)}</td>
    </tr>`;
  }).join("");
  $("#empty").classList.toggle("visible", state.servers.length === 0);
  document.querySelectorAll("#server-table [data-id]").forEach((row) => {
    row.onclick = () => { state.selected = row.dataset.id; switchView("analytics"); loadHeartbeats(state.selected); };
  });
}
function renderTimeline() {
  const target = $("#uptime-timeline");
  const start = new Date(state.availability?.from || Date.now() - 86400000).getTime();
  const end = new Date(state.availability?.to || Date.now()).getTime();
  target.innerHTML = (state.availability?.servers || []).map((server) => `
    <div class="timeline-row" data-id="${server.server_id}">
      <button><strong>${escapeHtml(server.name)}</strong><small>${server.uptime_percent == null ? "нет данных" : `${server.uptime_percent.toFixed(2)}%`}</small></button>
      <div class="timeline-track">${server.segments.map((segment) => {
        const left = (new Date(segment.from).getTime() - start) / (end - start) * 100;
        const width = (new Date(segment.to).getTime() - new Date(segment.from).getTime()) / (end - start) * 100;
        return `<i class="${segment.status}" style="left:${left}%;width:${Math.max(width, .15)}%" title="${segment.status === "up" ? "Доступен" : segment.status === "down" ? "Недоступен" : "Нет данных"}: ${formatTime(segment.from)} — ${formatTime(segment.to)}"></i>`;
      }).join("")}</div>
    </div>`).join("") || `<div class="empty-list visible"><strong>Нет зарегистрированных объектов</strong></div>`;
  const ticks = state.hours <= 24 ? 6 : state.hours <= 168 ? 7 : 6;
  $("#timeline-axis").innerHTML = Array.from({length: ticks + 1}, (_, i) => {
    const time = new Date(start + (end - start) * i / ticks);
    return `<span>${new Intl.DateTimeFormat("ru-RU", state.hours <= 24 ? {hour:"2-digit",minute:"2-digit"} : {day:"2-digit",month:"short"}).format(time)}</span>`;
  }).join("");
  document.querySelectorAll(".timeline-row").forEach((row) => {
    row.onclick = () => { state.selected = row.dataset.id; switchView("analytics"); loadHeartbeats(state.selected); };
  });
}
function renderIncidents() {
  const incidents = state.servers.filter((server) => server.status === "offline");
  text("#incident-count", `${incidents.length} активных`);
  $("#incident-list").innerHTML = incidents.map((server) => `<article class="incident"><i></i>
    <div><b>${escapeHtml(server.name)}</b><small>${escapeHtml(server.platform)} · heartbeat не поступает</small></div>
    <time>с ${formatTime(server.last_seen_at)}</time></article>`).join("");
  $("#no-incidents").classList.toggle("visible", incidents.length === 0);
}
function sparkline(values, fixedMax = null) {
  if (!values.length) return "";
  const min = fixedMax == null ? Math.min(...values) : 0;
  const max = fixedMax ?? Math.max(...values, min + 1);
  const range = Math.max(max - min, 1);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? 50 : index / (values.length - 1) * 100;
    const y = 92 - (value - min) / range * 78;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  return `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
    <polygon points="0,100 ${points} 100,100"></polygon><polyline points="${points}"></polyline>
  </svg>`;
}
function renderHeartbeatHealth(events) {
  if (!events.length) {
    $("#heartbeat-health").innerHTML = `<article class="panel empty-list visible"><strong>Heartbeat ещё не поступал</strong></article>`;
    return;
  }
  const ordered = [...events].reverse();
  const latest = ordered.at(-1);
  const expected = Number(latest.agent?.interval_seconds || 60);
  const gaps = ordered.slice(1).map((event, index) =>
    Math.max(0, (new Date(event.received_at) - new Date(ordered[index].received_at)) / 1000)
  );
  const maxGap = gaps.length ? Math.max(...gaps) : 0;
  const missed = gaps.reduce((total, gap) => total + Math.max(0, Math.floor(gap / expected) - 1), 0);
  const age = Math.max(0, Math.round((Date.now() - new Date(latest.received_at)) / 1000));
  const healthy = age <= expected * 3 && maxGap <= expected * 3;
  $("#heartbeat-health").innerHTML = `<article class="panel pulse-card ${healthy ? "healthy" : "warning"}">
    <div><p class="eyebrow">НАДЁЖНОСТЬ АГЕНТА</p><h2>${healthy ? "Heartbeat поступает стабильно" : "Есть задержки или пропуски"}</h2></div>
    <dl>
      <div><dt>Последний сигнал</dt><dd>${duration(age)} назад</dd></div>
      <div><dt>Ожидаемый интервал</dt><dd>${duration(expected)}</dd></div>
      <div><dt>Максимальный разрыв</dt><dd>${duration(maxGap)}</dd></div>
      <div><dt>Предполагаемые пропуски</dt><dd>${missed}</dd></div>
    </dl>
  </article>`;
}
function renderHistoryCharts(events) {
  const ordered = [...events].reverse();
  const definitions = [
    {label:"Нагрузка", key:"load_average_1m", unit:"", note:"load average за 1 минуту"},
    {label:"Память", key:"memory_usage_percent", unit:"%", note:"использование RAM", max:100},
    {label:"Диск /", key:"disk_usage_percent", unit:"%", note:"занято на корневом разделе", max:100},
  ];
  $("#history-charts").innerHTML = definitions.map((definition) => {
    const samples = ordered
      .map((event) => Number(event.system?.[definition.key]))
      .filter((value) => Number.isFinite(value));
    if (!samples.length) return `<article class="panel history-card no-data">
      <div><p>${definition.label}</p><strong>Нет истории</strong></div><small>Обновите агент для передачи этой метрики</small>
    </article>`;
    const latest = samples.at(-1);
    const minimum = Math.min(...samples);
    const maximum = Math.max(...samples);
    const warning = definition.key === "disk_usage_percent" && latest >= 90;
    return `<article class="panel history-card ${warning ? "warning" : ""}">
      <div class="history-head"><div><p>${definition.label}</p><strong>${latest.toFixed(definition.unit ? 1 : 2)}${definition.unit}</strong></div>
      <small>min ${minimum.toFixed(1)}${definition.unit} · max ${maximum.toFixed(1)}${definition.unit}</small></div>
      <div class="sparkline">${sparkline(samples, definition.max)}</div>
      <footer><span>${definition.note}</span><span>${samples.length} точек</span></footer>
    </article>`;
  }).join("");
}
function renderResources(latest = {}) {
  const system = latest.system || {}; const network = latest.network || {};
  const docker = (latest.services || []).find((item) => item.type === "docker") || {};
  const cards = [
    ["Нагрузка", system.load_average_1m ?? "—", system.cpu_count ? `на ${system.cpu_count} CPU` : "load average за 1 мин"],
    ["Память", system.memory_usage_percent == null ? "—" : `${system.memory_usage_percent}%`, `${bytes(system.memory_available_bytes)} свободно из ${bytes(system.memory_total_bytes)}`],
    ["Диск /", system.disk_usage_percent == null ? "—" : `${system.disk_usage_percent}%`, `${bytes(system.disk_available_bytes)} свободно из ${bytes(system.disk_total_bytes)}`],
    ["Docker", docker.total == null ? "нет данных" : `${docker.running}/${docker.total}`, docker.unhealthy ? `${docker.unhealthy} unhealthy` : "контейнеры без ошибок"],
    ["Сеть RX / TX", `${bytes(network.rx_bytes)} / ${bytes(network.tx_bytes)}`, "с момента загрузки системы"],
    ["Аптайм ОС", duration(system.uptime_seconds), `${system.kernel || "ядро неизвестно"} · ${system.process_count ?? "—"} процессов`],
  ];
  $("#resource-cards").innerHTML = cards.map(([label, value, note]) => `<article class="panel resource-card"><p>${label}</p><strong>${value}</strong><small>${note}</small></article>`).join("");
}
async function loadHeartbeats(id) {
  if (!id) return;
  state.selected = id; $("#analytics-server").value = id;
  const events = await api(`/api/v1/servers/${id}/heartbeats`);
  renderResources(events[0] || availabilityFor(id)?.latest || {});
  renderHeartbeatHealth(events);
  renderHistoryCharts(events);
}
function renderServerSelect() {
  $("#analytics-server").innerHTML = state.servers.map((server) => `<option value="${server.id}">${escapeHtml(server.name)}</option>`).join("");
  if (!state.selected && state.servers.length) state.selected = state.servers[0].id;
  if (state.selected) $("#analytics-server").value = state.selected;
}

const viewMeta = {
  overview: ["ЦЕНТР УПРАВЛЕНИЯ", "Состояние инфраструктуры"],
  objects: ["ИНФРАСТРУКТУРА", "Все устройства"],
  incidents: ["СОБЫТИЯ", "Инциденты и недоступность"],
  analytics: ["ДИАГНОСТИКА", "Ресурсы и телеметрия"],
  settings: ["УПРАВЛЕНИЕ", "Настройки системы"],
};
function switchView(view) {
  state.currentView = view;
  $("#metrics-section").classList.toggle("hidden-section", view !== "overview");
  $("#timeline-section").classList.toggle("hidden-section", view !== "overview");
  $("#analytics-section").classList.toggle("hidden-section", view !== "analytics");
  $("#objects-section").classList.toggle("hidden-section", view !== "overview" && view !== "objects");
  $("#incidents-section").classList.toggle("hidden-section", view !== "incidents");
  $("#settings-section").classList.toggle("hidden-section", view !== "settings");
  document.querySelectorAll("nav [data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  text("#page-eyebrow", viewMeta[view][0]); text("#page-title", viewMeta[view][1]);
  if (view === "analytics" && state.selected) loadHeartbeats(state.selected);
  window.history.replaceState(null, "", `#${view}`);
}
async function checkSystem() {
  const status = $("#settings-api-status"); status.textContent = "проверка…"; status.className = "";
  try {
    const ready = await api("/api/v1/health/ready"); status.textContent = ready.status === "ready" ? "доступен" : "деградация";
    status.className = ready.status === "ready" ? "ok" : "error-state"; await loadVersion(); showToast("Система проверена");
  } catch { status.textContent = "недоступен"; status.className = "error-state"; }
}
async function loadDashboard() {
  const [me, summary, servers, availability] = await Promise.all([
    api("/api/v1/auth/me"), api("/api/v1/dashboard/summary"), api("/api/v1/servers"),
    api(`/api/v1/dashboard/availability?hours=${state.hours}`),
  ]);
  $("#login-screen").classList.add("hidden"); state.currentUser = me; state.servers = servers; state.availability = availability;
  text("#current-user", me.login); text("#settings-user", me.login); text("#settings-role", me.role);
  renderSummary(summary); renderServers(); renderTimeline(); renderIncidents(); renderServerSelect();
  if (state.currentView === "analytics" && state.selected) await loadHeartbeats(state.selected);
}

document.querySelectorAll("nav [data-view]").forEach((button) => button.onclick = () => switchView(button.dataset.view));
document.querySelectorAll(".range-picker [data-hours]").forEach((button) => {
  button.onclick = async () => {
    state.hours = Number(button.dataset.hours);
    document.querySelectorAll(".range-picker button").forEach((item) => item.classList.toggle("active", item === button));
    await loadDashboard();
  };
});
document.querySelectorAll("[data-copy]").forEach((button) => {
  button.onclick = async () => { await navigator.clipboard.writeText($(button.dataset.copy).textContent); showToast("Команда скопирована"); };
});
$("#analytics-server").onchange = (event) => loadHeartbeats(event.target.value);
$("#add-device").onclick = () => { $("#device-modal").classList.remove("hidden"); $("#device-error").textContent = ""; };
$("#close-device-modal").onclick = () => $("#device-modal").classList.add("hidden");
$("#device-modal").onclick = (event) => { if (event.target === $("#device-modal")) $("#device-modal").classList.add("hidden"); };
$("#device-form").onsubmit = async (event) => {
  event.preventDefault(); const form = new FormData(event.currentTarget);
  $("#device-error").textContent = ""; $("#generated-command").classList.add("hidden");
  try {
    const bootstrap = await api("/api/v1/enrollment-tokens", {method:"POST", body:JSON.stringify({server_name:form.get("server_name"), platform:form.get("platform")})});
    text("#install-command", bootstrap.command); text("#command-expiry", formatTime(bootstrap.expires_at)); $("#generated-command").classList.remove("hidden");
    $("#bootstrap-warning").textContent = bootstrap.command.includes("localhost") ? "CLS_PUBLIC_URL указывает на localhost. Настройте публичный HTTPS-домен." : "Команда содержит одноразовый код. Не пересылайте её посторонним.";
  } catch (error) { $("#device-error").textContent = error.message === "unauthorized" ? "Сессия завершена — войдите снова." : "Не удалось создать команду."; }
};
$("#login-form").onsubmit = async (event) => {
  event.preventDefault(); const form = new FormData(event.currentTarget); $("#login-error").textContent = "";
  try { await api("/api/v1/auth/login", {method:"POST", body:JSON.stringify({login:form.get("login"),password:form.get("password")})}); await loadDashboard(); }
  catch { $("#login-error").textContent = "Неверный логин или пароль"; }
};
$("#logout").onclick = async () => { await api("/api/v1/auth/logout", {method:"POST"}); $("#login-screen").classList.remove("hidden"); };
$("#refresh").onclick = async () => { await loadDashboard(); showToast("Данные обновлены"); };
$("#check-system").onclick = checkSystem; $("#search").oninput = renderServers;
const initialView = window.location.hash.slice(1); switchView(viewMeta[initialView] ? initialView : "overview");
loadVersion(); loadDashboard().catch(() => {}); window.setInterval(() => loadDashboard().catch(() => {}), 30000);
