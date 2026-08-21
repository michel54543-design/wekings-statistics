const state = { page: 1, pages: 1, mode: "general", datesLoaded: false, playerDetail: null, finishedAt: undefined };
const metricNames = {
  glory: "Слава", stat_sum: "Сумма характеристик", power: "Сила",
  defense: "Защита", agility: "Ловкость", mastery: "Мастерство",
  vitality: "Живучесть", wins: "Победы", losses: "Поражения",
  dragon_wins: "Победы над Драконом", serpent_wins: "Победы над Змеем",
  beasts_killed: "Убито зверей", silver_stolen: "Награбил (серебро)",
  silver_lost: "Потерял (серебро)", crystals_stolen: "Награбил (кристаллы)",
  crystals_lost: "Потерял (кристаллы)",
  bandit_wins: "Победы над наемниками",
  mine: "Шахта",
  crusade: "Походы",
  quests: "Задания",
  pet_fights: "Бои питомца",
  pet_kills: "Убийства питомца",
  garden: "Участок",
  goblins: "Гоблины",
  lord_wins: "Победы над Владыкой",
  undead_wins: "Победы над нежитью",
  heroes_wins: "Победы над героями",
  serpent_fights: "Бои со Змеем",
  sent_gifts: "Отправлено подарков",
  fishing: "Рыбалка",
  dragon_kills: "Убийства Дракона",
  serpent_kills: "Убийства Змея"
};
const $ = (id) => document.getElementById(id);
const fmt = (v) => v == null ? "—" : Number(v).toLocaleString("ru-RU");
const dateText = (value) => new Date(value).toLocaleString("ru-RU", {day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"});
const detailMetricKeys = Object.keys(metricNames);
const rankBadge = rank => rank < 4
  ? `<span class="rank-medal place-${rank}">${rank}</span>`
  : `<span class="rank-number">${rank}</span>`;

function syncMobileNav() {
  document.querySelectorAll(".mobile-nav button").forEach(item => item.classList.remove("active"));
  if (["growth", "best"].includes(state.mode)) {
    document.querySelector('[data-mobile-mode="growth"]')?.classList.add("active");
  } else if (state.mode === "stats") {
    $("mobilePlayer")?.classList.add("active");
  } else {
    document.querySelector('[data-mobile-mode="general"]')?.classList.add("active");
  }
}

function fillLevels(maxLevel) {
  const maximum = Math.max(1, Number(maxLevel) || 44);
  const selected = $("level").value;
  $("level").innerHTML = '<option value="">Введите уровень</option>' +
    Array.from({ length: maximum }, (_, index) => maximum - index)
      .map(level => `<option value="${level}">${level} уровень</option>`)
      .join("");
  if (selected && Number(selected) <= maximum) $("level").value = selected;
}

function hidePlayerDetail() {
  state.playerDetail = null;
  $("playerDetail").classList.add("hidden");
  document.body.classList.remove("modal-open");
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

async function loadPlayerDetail(playerId, scroll = true) {
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
  document.body.classList.add("modal-open");
  renderPlayerDetail();
  $("closePlayerDetail").focus();
}

function attackTimeText(value, status) {
  if (value) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    }
  }
  return "Ожидаем новое время";
}

async function loadAttacks() {
  const box = $("attackSchedule");
  try {
    const response = await fetch(`/api/attacks?_=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    $("dragonTime").textContent = attackTimeText(data.dragon_at, data.dragon_status);
    $("serpentTime").textContent = attackTimeText(data.serpent_at, data.serpent_status);
    if (data.fetched_at) {
      $("attackUpdated").textContent = `обновлено ${new Date(data.fetched_at).toLocaleTimeString("ru-RU", {hour:"2-digit", minute:"2-digit"})}`;
    } else {
      $("attackUpdated").textContent = "";
    }
    box?.classList.toggle("waiting", !data.dragon_at || !data.serpent_at);
  } catch (error) {
    $("dragonTime").textContent = "Ожидаем новое время";
    $("serpentTime").textContent = "Ожидаем новое время";
    $("attackUpdated").textContent = "нет связи";
    box?.classList.add("waiting");
  }
}

async function loadStatus() {
  const data = await fetch("/api/status").then(r => r.json());
  $("statusText").textContent = data.running
    ? `Сейчас проверяется игрок №${fmt(data.current_player_id)}`
    : data.last_error ? "Обновление временно приостановлено — продолжится автоматически" : data.finished_at
      ? `Последнее обновление: ${new Date(data.finished_at).toLocaleString("ru-RU")}`
      : "Первый сбор данных ещё не запущен";
  if (state.finishedAt !== undefined && state.finishedAt !== data.finished_at && data.finished_at) {
    state.datesLoaded = false;
    await loadPlayers();
  }
  state.finishedAt = data.finished_at;
}

function fillDates(dates, selectedFrom, selectedTo) {
  if (!dates?.length) return;
  const dayKey = value => {
    const date = new Date(value);
    return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  };
  const seenDays = new Set();
  const dailyDates = dates.filter(value => {
    const key = dayKey(value);
    if (seenDays.has(key)) return false;
    seenDays.add(key);
    return true;
  });
  const snapshotDateText = value => new Date(value).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  });
  const options = dailyDates.map(value =>
    `<option value="${value}">Отчёт за ${snapshotDateText(value)}</option>`
  ).join("");
  $("dateFrom").innerHTML = options;
  $("dateTo").innerHTML = options;
  $("dateFrom").value = dailyDates.includes(selectedFrom)
    ? selectedFrom
    : dailyDates[Math.min(1, dailyDates.length - 1)];
  $("dateTo").value = dailyDates.includes(selectedTo) ? selectedTo : dailyDates[0];
  state.datesLoaded = true;
  if (["general", "stats", "clans", "brotherhoods"].includes(state.mode)) {
    $("toWrap").classList.remove("hidden");
  }
}

const isOrganizationMode = () => ["clans", "brotherhoods"].includes(state.mode);

function signedValue(value) {
  if (value == null || Number(value) === 0) return '<span class="change-zero">—</span>';
  const number = Number(value);
  return `<span class="${number > 0 ? "change-up" : "change-down"}">${number > 0 ? "+" : "−"}${fmt(Math.abs(number))}</span>`;
}

async function loadOrganizations() {
  const type = state.mode === "clans" ? "clan" : "brotherhood";
  const params = new URLSearchParams({ type, page: state.page, per_page: 50 });
  if (state.datesLoaded && $("dateTo").value) params.set("to", $("dateTo").value);
  $("rows").innerHTML = '<tr><td colspan="5" class="loading">Считаем рейтинг…</td></tr>';
  const data = await fetch(`/api/organizations?${params}`).then(r => r.json());
  if (!state.datesLoaded && data.dates?.length) fillDates(data.dates, data.date_from, data.date_to);
  state.pages = Math.max(1, data.pages || 1);
  const title = type === "clan" ? "Рейтинг кланов" : "Рейтинг братств";
  $("tableTitle").textContent = title;
  $("resultCount").textContent = `${fmt(data.total)} ${type === "clan" ? "кланов" : "братств"}`;
  $("rankingTable").className = "organization-table";
  $("tableHead").innerHTML = `<tr><th>№</th><th>${type === "clan" ? "Клан" : "Братство"}</th><th>Игроков</th><th>Сумма статов</th><th>Изменение</th></tr>`;
  $("pageText").textContent = `Страница ${data.page || 1} из ${state.pages}`;
  $("prev").disabled = state.page <= 1;
  $("next").disabled = state.page >= state.pages;
  if (!data.ready) {
    $("rows").innerHTML = '<tr><td colspan="5" class="loading">Рейтинг появится после двух завершённых снимков статистики</td></tr>';
    return;
  }
  $("rows").innerHTML = data.organizations.length ? data.organizations.map((group, i) => {
    const rank = (state.page - 1) * 50 + i + 1;
    const medal = rankBadge(rank);
    const members = group.members.map((member, memberIndex) => {
      const memberPlace = rankBadge(memberIndex + 1);
      return (
      `<div class="org-player">
        <b class="org-player-place">${memberPlace}</b>
        <a class="org-player-name game-profile-link" href="https://playwekings.mobi/hero/detail?player=${member.id}"><span>${escapeHtml(member.nickname)}</span></a>
        <small>ур. ${member.level ?? "—"} · ${fmt(member.stat_sum)}</small>
        <button class="show-stats" data-player-id="${member.id}" title="Показать статистику" aria-label="Показать статистику игрока">▥</button>
      </div>`
      );
    }).join("");
    const joined = group.joined.length
      ? `<div class="membership-list joined"><strong>Пришли:</strong> ${group.joined.map(member => escapeHtml(member.nickname)).join(", ")}</div>`
      : "";
    const left = group.left.length
      ? `<div class="membership-list left"><strong>Ушли:</strong> ${group.left.map(member => escapeHtml(member.nickname)).join(", ")}</div>`
      : "";
    return `<tr class="organization-row" data-org-index="${i}">
      <td class="rank">${medal}</td>
      <td class="organization-name"><button class="organization-toggle" aria-expanded="false"><span>▶</span>${escapeHtml(group.name)}</button></td>
      <td class="member-count">${group.member_count} ${signedValue(group.member_delta)}</td>
      <td class="value">${fmt(group.stat_sum)}</td>
      <td class="organization-change">${signedValue(group.stat_delta)}</td>
    </tr>
    <tr class="organization-members hidden" data-members-index="${i}">
      <td colspan="5">
        <div class="membership-changes">${joined}${left}</div>
        <div class="organization-player-list">${members}</div>
      </td>
    </tr>`;
  }).join("") : '<tr><td colspan="5" class="loading">Организации не найдены</td></tr>';
  hidePlayerDetail();
}

async function loadPlayers() {
  if (isOrganizationMode()) return loadOrganizations();
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
  fillLevels(data.max_level);
  if (!state.datesLoaded && data.dates?.length) fillDates(data.dates, data.date_from, data.date_to);
  state.pages = Math.max(1, data.pages);
  $("resultCount").textContent = `${fmt(data.total)} игроков`;
  const statsMode = state.mode === "stats";
  const prefix = state.mode === "general" ? "Рейтинг" : state.mode === "growth" ? "Прирост" : state.mode === "best" ? "Лучшие приросты" : "Все параметры";
  $("tableTitle").textContent = statsMode
    ? "Параметры всех игроков"
    : state.mode === "general" && sort === "power" ? "Рейтинг по силе" : `${prefix}: ${metricNames[sort]}`;
  $("rankingTable").classList.remove("organization-table");
  $("rankingTable").classList.toggle("stats-table", statsMode);
  $("tableHead").innerHTML = statsMode
    ? '<tr><th>№</th><th>Игрок</th><th>Сила</th><th>Защита</th><th>Ловкость</th><th>Мастерство</th><th>Живучесть</th></tr>'
    : `<tr><th>№</th><th>Игрок</th><th>Ур.</th><th>Братство</th><th>Клан</th><th id="metricTitle">${state.mode === "general" ? metricNames[sort] : "Прирост"}</th><th>Прирост</th></tr>`;
  $("pageText").textContent = `Страница ${data.page} из ${state.pages}`;
  $("prev").disabled = state.page <= 1;
  $("next").disabled = state.page >= state.pages;
  $("rows").innerHTML = data.players.length ? data.players.map((p, i) => {
    const rank = (state.page - 1) * 50 + i + 1;
    const medal = rankBadge(rank);
    if (statsMode) {
      return `<tr class="stats-row">
        <td class="rank">${medal}</td>
        <td class="player-name"><a href="${escapeHtml(p.profile_url)}" class="game-profile-link">${escapeHtml(p.nickname)}</a><button class="show-stats" data-player-id="${p.id}" title="Показать статистику" aria-label="Показать статистику игрока">▥</button><small>${p.level ?? "—"}</small></td>
        <td class="stat-number">${fmt(p.power)}</td>
        <td class="stat-number">${fmt(p.defense)}</td>
        <td class="stat-number">${fmt(p.agility)}</td>
        <td class="stat-number">${fmt(p.mastery)}</td>
        <td class="stat-number">${fmt(p.vitality)}</td>
      </tr>`;
    }
    const mainValue = state.mode === "general" ? p[sort] : p.gain;
    const gain = p.gain;
    return `<tr>
      <td class="rank" data-label="Место">${medal}</td>
      <td class="player-name" data-label="Игрок"><a href="${escapeHtml(p.profile_url)}" class="game-profile-link">${escapeHtml(p.nickname)}</a><button class="show-stats" data-player-id="${p.id}" title="Показать статистику" aria-label="Показать статистику игрока">▥</button><b class="mobile-level">${p.level ?? "—"}</b></td>
      <td data-label="Уровень"><b class="level">${p.level ?? "—"}</b></td>
      <td class="group" data-label="Братство">${escapeHtml(p.brotherhood || "—")}</td>
      <td class="group" data-label="Клан">${escapeHtml(p.clan || "—")}</td>
      <td class="value" data-label="${metricNames[sort]}">${state.mode === "general" ? fmt(mainValue) : (mainValue == null ? "—" : `+${fmt(mainValue)}`)}</td>
      <td class="${gain > 0 ? "gain" : "muted"}" data-label="Прирост">${gain > 0 ? `+${fmt(gain)}` : "—"}</td>
    </tr>`;
  }).join("") : `<tr><td colspan="7" class="loading">${data.dates?.length < 2 && state.mode !== "general" ? "Прирост появится после второго снимка статистики" : "Игроки не найдены"}</td></tr>`;
  const query = $("query").value.trim();
  const exactPlayer = query
    ? data.players.find(player => player.nickname.toLocaleLowerCase("ru-RU") === query.toLocaleLowerCase("ru-RU"))
    : null;
  const searchedPlayer = exactPlayer || (query && data.players.length === 1 ? data.players[0] : null);
  if (searchedPlayer) {
    loadPlayerDetail(searchedPlayer.id, false).catch(hidePlayerDetail);
  } else {
    hidePlayerDetail();
  }
}


const lifeState = { period: "now", loaded: false };
function lifeDateText(value) {
  return new Date(value).toLocaleString("ru-RU",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
}
async function loadLife(period=lifeState.period) {
  lifeState.period=period;
  document.querySelectorAll("[data-life-period]").forEach(b=>b.classList.toggle("active",b.dataset.lifePeriod===period));
  $("lifeEvents").innerHTML='<p class="life-empty">Собираем события…</p>';
  const data=await fetch(`/api/life?period=${encodeURIComponent(period)}`).then(r=>r.json());
  if(!data.ready){$("lifeRange").textContent="Нужно минимум два завершённых снимка";$("lifeHeroes").innerHTML="";$("lifeEvents").innerHTML='<p class="life-empty">Пока недостаточно данных.</p>';return;}
  $("lifeRange").textContent=`${lifeDateText(data.from_date)} → ${lifeDateText(data.to_date)}`;
  $("lifeHeroes").innerHTML=data.heroes?.length?data.heroes.slice(0,4).map(h=>`<article class="life-hero"><span>${h.icon} ${escapeHtml(h.label)}</span><strong>${escapeHtml(h.nickname)}</strong><b>+${fmt(h.gain)}</b></article>`).join(""):"";
  $("lifeEvents").innerHTML=data.events?.length?data.events.map(e=>`<article class="life-event"><span class="life-event-icon">${e.icon}</span><div><a class="game-profile-link" href="https://playwekings.mobi/hero/detail?player=${e.player_id}">${escapeHtml(e.nickname)}</a><p>${escapeHtml(e.text)}</p></div></article>`).join(""):'<p class="life-empty">За выбранный период заметных изменений нет.</p>';
  lifeState.loaded=true;
}
function openLife(){$("lifePanel").classList.remove("hidden");$("lifeToggle").classList.add("active");$("lifeToggle").setAttribute("aria-expanded","true");if(!lifeState.loaded)loadLife().catch(()=>{$("lifeEvents").innerHTML='<p class="life-empty">Не удалось загрузить события.</p>';});$("lifePanel").scrollIntoView({behavior:"smooth",block:"start"});}
function closeLife(){$("lifePanel").classList.add("hidden");$("lifeToggle").classList.remove("active");$("lifeToggle").setAttribute("aria-expanded","false");}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

document.querySelectorAll(".modes button").forEach(button => {
  button.onclick = () => {
    document.querySelectorAll(".modes button").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.mode = button.dataset.mode;
    syncMobileNav();
    const growthDates = state.mode === "growth" && state.datesLoaded;
    const generalDate = ["general", "stats", "clans", "brotherhoods"].includes(state.mode) && state.datesLoaded;
    $("fromWrap").classList.toggle("hidden", !growthDates);
    $("toWrap").classList.toggle("hidden", !(growthDates || generalDate));
    $("toLabel").textContent = state.mode === "growth" ? "До" : "Снимок данных";
    const organizations = isOrganizationMode();
    $("sort").closest("label").classList.toggle("hidden", state.mode === "stats" || organizations);
    $("level").closest("label").classList.toggle("hidden", organizations);
    $("query").closest("label").classList.toggle("hidden", organizations);
    $("find").classList.toggle("hidden", organizations);
    state.page = 1;
    loadPlayers();
  };
});
$("find").onclick = () => { state.page = 1; loadPlayers(); };
$("query").onkeydown = (e) => { if (e.key === "Enter") { state.page = 1; loadPlayers(); } };
$("sort").onchange = () => { state.page = 1; loadPlayers(); };
$("level").onchange = () => { state.page = 1; loadPlayers(); };
$("dateFrom").onchange = () => { state.page = 1; loadPlayers(); };
$("dateTo").onchange = () => { state.page = 1; loadPlayers(); };
$("detailFrom").onchange = renderPlayerDetail;
$("detailTo").onchange = renderPlayerDetail;
$("prev").onclick = () => { if (state.page > 1) { state.page--; loadPlayers(); } };
$("next").onclick = () => { if (state.page < state.pages) { state.page++; loadPlayers(); } };
$("filterToggle").onclick = () => {
  $("filters").classList.toggle("mobile-open");
  $("filterToggle").classList.toggle("active");
};
document.addEventListener("click", event => {
  const statsButton = event.target.closest(".show-stats");
  if (statsButton) {
    event.preventDefault();
    event.stopImmediatePropagation();
    loadPlayerDetail(statsButton.dataset.playerId, false).catch(hidePlayerDetail);
    return;
  }
  if (event.target === $("playerDetail") || event.target.closest("#closePlayerDetail")) {
    hidePlayerDetail();
    return;
  }
  const gameProfileLink = event.target.closest(".game-profile-link");
  if (gameProfileLink) {
    event.preventDefault();
    event.stopImmediatePropagation();
    window.location.assign(gameProfileLink.href);
    return;
  }
  const organizationToggle = event.target.closest(".organization-toggle");
  if (organizationToggle) {
    const row = organizationToggle.closest(".organization-row");
    const membersRow = document.querySelector(`[data-members-index="${row.dataset.orgIndex}"]`);
    const willOpen = membersRow.classList.contains("hidden");
    membersRow.classList.toggle("hidden", !willOpen);
    organizationToggle.setAttribute("aria-expanded", String(willOpen));
    organizationToggle.querySelector("span").textContent = willOpen ? "▼" : "▶";
    return;
  }
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !$("playerDetail").classList.contains("hidden")) hidePlayerDetail();
});
document.querySelectorAll("[data-mobile-mode]").forEach(button => {
  button.onclick = () => {
    document.querySelector(`.modes button[data-mode="${button.dataset.mobileMode}"]`)?.click();
    document.querySelector(".modes").scrollIntoView({ behavior: "smooth" });
  };
});
$("mobilePlayer").onclick = () => {
  document.querySelector('.modes button[data-mode="stats"]')?.click();
  if (!$("playerDetail").classList.contains("hidden")) {
    return;
  } else {
    $("filters").classList.add("mobile-open");
    $("query").focus();
    $("filters").scrollIntoView({ behavior: "smooth" });
  }
};


$("lifeToggle").onclick=()=>{$("lifePanel").classList.contains("hidden")?openLife():closeLife();};
$("lifeClose").onclick=closeLife;
document.querySelectorAll("[data-life-period]").forEach(b=>{b.onclick=()=>loadLife(b.dataset.lifePeriod).catch(()=>{$("lifeEvents").innerHTML='<p class="life-empty">Не удалось загрузить события.</p>';});});

$("todayBadge").textContent = new Date().toLocaleDateString("ru-RU", {
  day: "2-digit", month: "short"
}).replace(".", "").toUpperCase();
syncMobileNav();
loadStatus().catch(() => {});
loadAttacks().catch(() => {});
loadPlayers().catch(() => $("rows").innerHTML = '<tr><td colspan="7" class="loading">Не удалось загрузить данные</td></tr>');
setInterval(() => loadStatus().catch(() => {}), 30000);
setInterval(() => loadAttacks().catch(() => {}), 60000);
