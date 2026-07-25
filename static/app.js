const state = { page: 1, pages: 1, mode: "general", datesLoaded: false, playerDetail: null };
const metricNames = {
  glory: "Слава", stat_sum: "Сумма характеристик", power: "Сила",
  defense: "Защита", agility: "Ловкость", mastery: "Мастерство",
  vitality: "Живучесть", wins: "Победы", losses: "Поражения",
  dragon_wins: "Победы над Драконом", serpent_wins: "Победы над Змеем",
  beasts_killed: "Убито зверей", silver_stolen: "Награбил (серебро)",
  silver_lost: "Потерял (серебро)", crystals_stolen: "Награбил (кристаллы)",
  crystals_lost: "Потерял (кристаллы)"
};
const $ = (id) => document.getElementById(id);
const fmt = (v) => v == null ? "—" : Number(v).toLocaleString("ru-RU");
const dateText = (value) => new Date(value).toLocaleString("ru-RU", {day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"});
const detailMetricKeys = Object.keys(metricNames);

function hidePlayerDetail() {
  state.playerDetail = null;
  $("playerDetail").classList.add("hidden");
}

function renderPlayerDetail() {
  const player = state.playerDetail;
  if (!player?.history?.length) return hidePlayerDetail();
  const fromIndex = Math.max(0, Number($("detailFrom").value || 0));
  const toIndex = Math.max(0, Number($("detailTo").value || player.history.length - 1));
  const from = player.history[Math.min(fromIndex, toIndex)];
  const to = player.history[Math.max(fromIndex, toIndex)];
  $("detailMetrics").innerHTML = detailMetricKeys.map(key => {
    const current = to[key];
    const delta = current == null || from[key] == null ? null : Number(current) - Number(from[key]);
    const deltaClass = delta > 0 ? "up" : delta < 0 ? "down" : "zero";
    const deltaText = delta == null ? "нет данных" : delta > 0 ? `+${fmt(delta)}` : fmt(delta);
    return `<article class="metric-card">
      <span>${metricNames[key]}</span>
      <strong>${fmt(current)}</strong>
      <small class="delta ${deltaClass}">${deltaText}</small>
    </article>`;
  }).join("");
}

async function loadPlayerDetail(playerId) {
  const player = await fetch(`/api/player/${playerId}`).then(r => {
    if (!r.ok) throw new Error("Игрок не найден");
    return r.json();
  });
  state.playerDetail = player;
  $("detailName").textContent = player.nickname;
  $("detailMeta").innerHTML = [
    `Уровень ${player.level ?? "—"}`,
    player.brotherhood ? `Братство: ${escapeHtml(player.brotherhood)}` : "",
    player.clan ? `Клан: ${escapeHtml(player.clan)}` : ""
  ].filter(Boolean).map(value => `<span>${value}</span>`).join("");
  $("detailProfile").href = player.profile_url;
  const options = player.history.map((item, index) =>
    `<option value="${index}">${dateText(item.date)}</option>`
  ).join("");
  $("detailFrom").innerHTML = options;
  $("detailTo").innerHTML = options;
  $("detailFrom").value = Math.max(0, player.history.length - 2);
  $("detailTo").value = player.history.length - 1;
  $("playerDetail").classList.remove("hidden");
  renderPlayerDetail();
}

async function loadStatus() {
  const data = await fetch("/api/status").then(r => r.json());
  $("totalPlayers").textContent = fmt(data.total_players);
  $("progress").textContent = data.max_player_id
    ? `${fmt(Math.min(data.current_player_id, data.max_player_id))} / ${fmt(data.max_player_id)}`
    : "Ожидание";
  $("statusText").textContent = data.running
    ? `Сейчас проверяется игрок №${fmt(data.current_player_id)}`
    : data.last_error ? `Сбор остановлен: ${data.last_error}` : data.finished_at
      ? `Последнее обновление: ${new Date(data.finished_at).toLocaleString("ru-RU")}`
      : "Первый сбор данных ещё не запущен";
}

function fillDates(dates, selectedFrom, selectedTo) {
  if (!dates?.length) return;
  const options = dates.map(value => `<option value="${value}">${dateText(value)}</option>`).join("");
  $("dateFrom").innerHTML = options;
  $("dateTo").innerHTML = options;
  $("dateFrom").value = selectedFrom || dates[Math.min(1, dates.length - 1)];
  $("dateTo").value = selectedTo || dates[0];
  state.datesLoaded = true;
  if (state.mode === "general") $("toWrap").classList.remove("hidden");
}

async function loadPlayers() {
  const sort = $("sort").value;
  const params = new URLSearchParams({ page: state.page, per_page: 50, sort, mode: state.mode });
  if ($("query").value.trim()) params.set("q", $("query").value.trim());
  if ($("level").value) params.set("level", $("level").value);
  if (state.datesLoaded && state.mode !== "best") {
    params.set("to", $("dateTo").value);
    if (state.mode === "growth") params.set("from", $("dateFrom").value);
  }
  $("rows").innerHTML = '<tr><td colspan="7" class="loading">Загрузка…</td></tr>';
  const data = await fetch(`/api/players?${params}`).then(r => r.json());
  if (!state.datesLoaded && data.dates?.length) fillDates(data.dates, data.date_from, data.date_to);
  state.pages = Math.max(1, data.pages);
  $("resultCount").textContent = `${fmt(data.total)} игроков`;
  const prefix = state.mode === "general" ? "Рейтинг" : state.mode === "growth" ? "Прирост" : "Лучшие приросты";
  $("tableTitle").textContent = `${prefix}: ${metricNames[sort]}`;
  $("metricTitle").textContent = state.mode === "general" ? metricNames[sort] : "Прирост";
  $("pageText").textContent = `Страница ${data.page} из ${state.pages}`;
  $("prev").disabled = state.page <= 1;
  $("next").disabled = state.page >= state.pages;
  $("rows").innerHTML = data.players.length ? data.players.map((p, i) => {
    const rank = (state.page - 1) * 50 + i + 1;
    const medal = rank < 4 ? ["🥇","🥈","🥉"][rank - 1] : rank;
    const mainValue = state.mode === "general" ? p[sort] : p.gain;
    const gain = p.gain;
    return `<tr>
      <td class="rank">${medal}</td>
      <td><a href="${p.profile_url}" target="_blank" rel="noreferrer">${escapeHtml(p.nickname)}</a></td>
      <td><b class="level">${p.level ?? "—"}</b></td>
      <td class="group">${escapeHtml(p.brotherhood || "—")}</td>
      <td class="group">${escapeHtml(p.clan || "—")}</td>
      <td class="value">${state.mode === "general" ? fmt(mainValue) : (mainValue == null ? "—" : `+${fmt(mainValue)}`)}</td>
      <td class="${gain > 0 ? "gain" : "muted"}">${gain > 0 ? `+${fmt(gain)}` : "—"}</td>
    </tr>`;
  }).join("") : `<tr><td colspan="7" class="loading">${data.dates?.length < 2 && state.mode !== "general" ? "Прирост появится после второго снимка статистики" : "Игроки не найдены"}</td></tr>`;
  const query = $("query").value.trim();
  if (query && data.players.length === 1) {
    loadPlayerDetail(data.players[0].id).catch(hidePlayerDetail);
  } else {
    hidePlayerDetail();
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

document.querySelectorAll(".modes button").forEach(button => {
  button.onclick = () => {
    document.querySelectorAll(".modes button").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.mode = button.dataset.mode;
    const growthDates = state.mode === "growth" && state.datesLoaded;
    const generalDate = state.mode === "general" && state.datesLoaded;
    $("fromWrap").classList.toggle("hidden", !growthDates);
    $("toWrap").classList.toggle("hidden", !(growthDates || generalDate));
    $("toLabel").textContent = state.mode === "growth" ? "До" : "Снимок данных";
    state.page = 1;
    loadPlayers();
  };
});
$("find").onclick = () => { state.page = 1; loadPlayers(); };
$("query").onkeydown = (e) => { if (e.key === "Enter") { state.page = 1; loadPlayers(); } };
$("sort").onchange = () => { state.page = 1; loadPlayers(); };
$("dateFrom").onchange = () => { state.page = 1; loadPlayers(); };
$("dateTo").onchange = () => { state.page = 1; loadPlayers(); };
$("detailFrom").onchange = renderPlayerDetail;
$("detailTo").onchange = renderPlayerDetail;
$("prev").onclick = () => { if (state.page > 1) { state.page--; loadPlayers(); } };
$("next").onclick = () => { if (state.page < state.pages) { state.page++; loadPlayers(); } };
$("theme").onclick = () => document.body.classList.toggle("dark");

loadStatus().catch(() => {});
loadPlayers().catch(() => $("rows").innerHTML = '<tr><td colspan="7" class="loading">Не удалось загрузить данные</td></tr>');
setInterval(() => loadStatus().catch(() => {}), 30000);
