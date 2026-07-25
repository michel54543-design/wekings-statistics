const state = { page: 1, pages: 1 };
const metricNames = {
  glory: "Слава", stat_sum: "Сумма характеристик", power: "Сила",
  defense: "Защита", agility: "Ловкость", mastery: "Мастерство",
  vitality: "Живучесть", wins: "Победы", losses: "Поражения",
  dragon_wins: "Победы над Драконом", serpent_wins: "Победы над Змеем"
};
const $ = (id) => document.getElementById(id);
const fmt = (v) => v == null ? "—" : Number(v).toLocaleString("ru-RU");

async function loadStatus() {
  const data = await fetch("/api/status").then(r => r.json());
  $("totalPlayers").textContent = fmt(data.total_players);
  $("progress").textContent = data.max_player_id
    ? `${fmt(Math.min(data.current_player_id, data.max_player_id))} / ${fmt(data.max_player_id)}`
    : "Ожидание";
  $("statusText").textContent = data.running
    ? `Сейчас проверяется игрок №${fmt(data.current_player_id)}`
    : data.finished_at ? `Последнее обновление: ${new Date(data.finished_at).toLocaleString("ru-RU")}` : "Первый сбор данных";
}

async function loadPlayers() {
  const sort = $("sort").value;
  const params = new URLSearchParams({ page: state.page, per_page: 50, sort });
  if ($("query").value.trim()) params.set("q", $("query").value.trim());
  if ($("level").value) params.set("level", $("level").value);
  $("rows").innerHTML = '<tr><td colspan="6" class="loading">Загрузка…</td></tr>';
  const data = await fetch(`/api/players?${params}`).then(r => r.json());
  state.pages = Math.max(1, data.pages);
  $("resultCount").textContent = `${fmt(data.total)} игроков`;
  $("tableTitle").textContent = `Рейтинг: ${metricNames[sort]}`;
  $("metricTitle").textContent = metricNames[sort];
  $("pageText").textContent = `Страница ${data.page} из ${state.pages}`;
  $("prev").disabled = state.page <= 1;
  $("next").disabled = state.page >= state.pages;
  $("rows").innerHTML = data.players.length ? data.players.map((p, i) => {
    const rank = (state.page - 1) * 50 + i + 1;
    const medal = rank < 4 ? ["🥇","🥈","🥉"][rank - 1] : rank;
    const group = p.brotherhood || p.clan || "—";
    const value = p[sort];
    const gain = sort === "glory" ? p.glory_gain : (sort === "stat_sum" ? p.stats_gain : null);
    return `<tr>
      <td class="rank">${medal}</td>
      <td><a href="${p.profile_url}" target="_blank" rel="noreferrer">${escapeHtml(p.nickname)}</a></td>
      <td><b class="level">${p.level ?? "—"}</b></td>
      <td class="group">${escapeHtml(group)}</td>
      <td class="value">${fmt(value)}</td>
      <td class="${gain > 0 ? "gain" : "muted"}">${gain > 0 ? `+${fmt(gain)}` : "—"}</td>
    </tr>`;
  }).join("") : '<tr><td colspan="6" class="loading">Игроки не найдены</td></tr>';
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

$("find").onclick = () => { state.page = 1; loadPlayers(); };
$("query").onkeydown = (e) => { if (e.key === "Enter") { state.page = 1; loadPlayers(); } };
$("sort").onchange = () => { state.page = 1; loadPlayers(); };
$("prev").onclick = () => { if (state.page > 1) { state.page--; loadPlayers(); } };
$("next").onclick = () => { if (state.page < state.pages) { state.page++; loadPlayers(); } };
$("theme").onclick = () => document.body.classList.toggle("dark");

loadStatus().catch(() => {});
loadPlayers().catch(() => $("rows").innerHTML = '<tr><td colspan="6" class="loading">Не удалось загрузить данные</td></tr>');
setInterval(() => loadStatus().catch(() => {}), 30000);
