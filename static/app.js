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

function attackTimeText(value, stayMinutes) {
  if (!value) return "Ожидаем новое время";
  const start = new Date(value);
  if (Number.isNaN(start.getTime())) return "Ожидаем новое время";
  const now = new Date();
  const end = new Date(start.getTime() + stayMinutes * 60000);
  if (now < start) return start.toLocaleTimeString("ru-RU", {hour:"2-digit", minute:"2-digit"});
  if (now < end) return "Сейчас в городе";
  return "Ожидаем новое время";
}

function weatherTimeText(value) {
  if (!value) return "Нет прогноза";
  const date = new Date(value);
  if (Number.isNaN(date.getTime()) || new Date() > date) return "Нет прогноза";
  return date.toLocaleString("ru-RU", {day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"});
}

async function refreshAttacks() {
  const button = $("attackRefresh");
  if (!button) return;

  const before = window.__attacksFetchedAt || null;
  button.disabled = true;
  button.textContent = "Обновляем…";

  try {
    const response = await fetch("/api/attacks/refresh", { method: "POST", cache: "no-store" });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data?.message || `HTTP ${response.status}`);

    for (let i = 0; i < 20; i++) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      const check = await fetch(`/api/attacks?_=${Date.now()}`, { cache: "no-store" });
      if (!check.ok) continue;
      const fresh = await check.json();
      if (fresh.fetched_at && fresh.fetched_at !== before) {
        await loadAttacks();
        return;
      }
    }
    await loadAttacks();
  } catch (error) {
    button.title = error?.message || "Не удалось обновить прогноз";
  } finally {
    button.disabled = false;
    button.textContent = "↻ Обновить";
  }
}


async function loadAttacks() {
  const box = $("attackSchedule");
  try {
    const response = await fetch(`/api/attacks?_=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    $("dragonTime").textContent = attackTimeText(data.dragon_at, 60);
    $("serpentTime").textContent = attackTimeText(data.serpent_at, 90);
    $("weatherTime").textContent = weatherTimeText(data.weather_at);
    window.__attacksFetchedAt = data.fetched_at || null;
    if (data.fetched_at) {
      $("attackUpdated").textContent = `обновлено ${new Date(data.fetched_at).toLocaleTimeString("ru-RU", {hour:"2-digit", minute:"2-digit"})}`;
    } else {
      $("attackUpdated").textContent = "";
    }
    box?.classList.toggle("waiting", !data.dragon_at || !data.serpent_at);
  } catch (error) {
    $("dragonTime").textContent = "Ожидаем новое время";
    $("serpentTime").textContent = "Ожидаем новое время";
    $("weatherTime").textContent = "Нет прогноза";
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


const levelGroupState = { open: new Set(), cache: new Map() };

function levelPlayerCard(player, index) {
  return `<div class="level-player-card">
    <div class="level-player-name"><span>${index + 1}</span><a class="game-profile-link" href="${escapeHtml(player.profile_url)}">${escapeHtml(player.nickname)}</a></div>
    <div class="level-player-stat"><small>Сила</small><b>${fmt(player.power)}</b></div>
    <div class="level-player-stat"><small>Защита</small><b>${fmt(player.defense)}</b></div>
    <div class="level-player-stat"><small>Ловкость</small><b>${fmt(player.agility)}</b></div>
    <div class="level-player-stat"><small>Мастерство</small><b>${fmt(player.mastery)}</b></div>
    <div class="level-player-stat"><small>Живучесть</small><b>${fmt(player.vitality)}</b></div>
  </div>`;
}

async function loadLevelPlayers(level, target, toDate) {
  target.innerHTML = '<div class="level-loading">Загрузка игроков уровня…</div>';
  try {
    const params = new URLSearchParams({ level, to: toDate || "" });
    const q = $("query").value.trim();
    if (q) params.set("q", q);
    const data = await fetch(`/api/level-players?${params}`).then(r => r.json());
    if (!data.players?.length) {
      target.innerHTML = '<div class="level-loading">Игроки не найдены</div>';
      return;
    }
    target.innerHTML = `<div class="level-player-header"><span>Игрок</span><span>Сила</span><span>Защита</span><span>Ловкость</span><span>Мастерство</span><span>Живучесть</span></div>${data.players.map(levelPlayerCard).join("")}`;
    levelGroupState.cache.set(level, data.players);
  } catch (error) {
    target.innerHTML = '<div class="level-loading">Не удалось загрузить игроков</div>';
  }
}

async function loadLevelGroups() {
  $("tableTitle").textContent = "Едина по уровням";
  $("resultCount").textContent = "";
  $("rankingTable").className = "levels-table";
  $("tableHead").innerHTML = '<tr><th>Уровень</th><th>Игроков</th><th>Сила</th><th>Статус</th></tr>';
  $("rows").innerHTML = '<tr><td colspan="4" class="loading">Загружаем уровни…</td></tr>';
  const params = new URLSearchParams();
  if (state.datesLoaded && $("dateTo").value) params.set("to", $("dateTo").value);
  const q = $("query").value.trim();
  if (q) params.set("q", q);
  try {
    const data = await fetch(`/api/level-groups?${params}`).then(r => r.json());
    if (!state.datesLoaded && data.dates?.length) fillDates(data.dates, data.date_from, data.date_to);
    if (!data.levels?.length) {
      $("rows").innerHTML = '<tr><td colspan="4" class="loading">Уровни не найдены</td></tr>';
      return;
    }
    $("resultCount").textContent = `${fmt(data.levels.reduce((sum, x) => sum + x.count, 0))} игроков`;
    $("pageText").textContent = `${data.levels.length} уровней`;
    $("prev").disabled = true;
    $("next").disabled = true;
    $("rows").innerHTML = data.levels.map(item => {
      const open = levelGroupState.open.has(item.level);
      const up = item.up || [];
      const down = item.down || [];
      const upText = up.length ? `<div class="level-change up"><b>🟢 Поднялись:</b> ${up.map(escapeHtml).join(", ")}</div>` : "";
      const downText = down.length ? `<div class="level-change down"><b>🔴 Ушли:</b> ${down.map(escapeHtml).join(", ")}</div>` : "";
      return `<tr class="level-group-row ${open ? "open" : ""}" data-level="${item.level}">
        <td class="level-group-title"><button class="level-toggle" type="button" aria-expanded="${open}">▶</button><b>Уровень ${item.level}</b></td>
        <td>${fmt(item.count)}</td>
        <td>—</td>
        <td>${up.length ? `<span class="level-up">+${up.length}</span>` : ""}${down.length ? `<span class="level-down">−${down.length}</span>` : ""}${!up.length && !down.length ? "—" : ""}</td>
      </tr>
      <tr class="level-detail-row ${open ? "" : "hidden"}" data-level-detail="${item.level}"><td colspan="4"><div class="level-changes">${upText}${downText}</div><div class="level-players-wrap">${open ? '<div class="level-loading">Загрузка игроков уровня…</div>' : ""}</div></td></tr>`;
    }).join("");

    document.querySelectorAll(".level-group-row").forEach(row => {
      row.querySelector(".level-toggle").addEventListener("click", async () => {
        const level = Number(row.dataset.level);
        const detail = document.querySelector(`[data-level-detail="${level}"]`);
        const button = row.querySelector(".level-toggle");
        const willOpen = detail.classList.contains("hidden");
        button.setAttribute("aria-expanded", String(willOpen));
        button.textContent = willOpen ? "▼" : "▶";
        row.classList.toggle("open", willOpen);
        detail.classList.toggle("hidden", !willOpen);
        if (willOpen) {
          levelGroupState.open.add(level);
          await loadLevelPlayers(level, detail.querySelector(".level-players-wrap"), data.date_to);
        } else {
          levelGroupState.open.delete(level);
        }
      });
    });

    // Открытые уровни не закрываем при обновлении/фильтрации.
    for (const level of levelGroupState.open) {
      const detail = document.querySelector(`[data-level-detail="${level}"]`);
      if (detail) loadLevelPlayers(level, detail.querySelector(".level-players-wrap"), data.date_to);
    }
  } catch (error) {
    $("rows").innerHTML = '<tr><td colspan="4" class="loading">Не удалось загрузить уровни</td></tr>';
  }
}

async function loadPlayers() {
  if (isOrganizationMode()) return loadOrganizations();
  if (state.mode === "stats") return loadLevelGroups();
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
  const prefix = state.mode === "general" ? "Рейтинг" : state.mode === "growth" ? "Прирост" : state.mode === "best" ? "Лучшие приросты" : "Едина по уровням";
  if (statsMode) {
    return loadLevelGroups();
  }
  $("tableTitle").textContent = state.mode === "general" && sort === "power" ? "Рейтинг по силе" : `${prefix}: ${metricNames[sort]}`;
  $("rankingTable").classList.remove("organization-table", "stats-table", "levels-table");
  $("tableHead").innerHTML = `<tr><th>№</th><th>Игрок</th><th>Ур.</th><th>Братство</th><th>Клан</th><th id="metricTitle">${state.mode === "general" ? metricNames[sort] : "Прирост"}</th><th>Прирост</th></tr>`;
  $("pageText").textContent = `Страница ${data.page} из ${state.pages}`;
  $("prev").disabled = state.page <= 1;
  $("next").disabled = state.page >= state.pages;
  $("rows").innerHTML = data.players.length ? data.players.map((p, i) => {
    const rank = (state.page - 1) * 50 + i + 1;
    const medal = rankBadge(rank);
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

async function loadLifeSummary() {
  const data = await fetch("/api/life-summary").then(r => r.json());
  if (!data.ready) return;
  const s = data.summary || {};
  $("lifeDailySummary").innerHTML = `
    <div><b>📊 ${fmt(s.active_players)}</b><span>активных игроков</span></div>`;
  const h = data.hero;
  if (h) {
    const achievements = [];
    if (h.bandit_gain) achievements.push(`⚔️ ${fmt(h.bandit_gain)} побед над наёмниками`);
    if (h.stat_gain) achievements.push(`💪 +${fmt(h.stat_gain)} характеристик`);
    if (h.mine_gain) achievements.push(`⛏️ +${fmt(h.mine_gain)} шахта`);
    if (h.power_gain) achievements.push(`⚡ +${fmt(h.power_gain)} силы`);
    if (h.dragon_gain) achievements.push(`🐉 ${fmt(h.dragon_gain)} побед над Драконом`);
    if (h.serpent_gain) achievements.push(`🐍 ${fmt(h.serpent_gain)} побед над Змеем`);
    if (h.quests_gain) achievements.push(`📜 +${fmt(h.quests_gain)} заданий`);
    if (h.wins_gain) achievements.push(`🏆 +${fmt(h.wins_gain)} побед`);
    $("lifeHeroDay").innerHTML = `
      <header><span>👑</span><div><small>ГЕРОЙ ДНЯ</small><strong>${escapeHtml(h.nickname)}</strong></div></header>
      <div class="life-hero-reasons">${achievements.slice(0,4).map(x => `<div>${x}</div>`).join("")}</div>
      <p><b>За наибольшую активность сегодня</b></p>
      <a class="game-profile-link" href="https://playwekings.mobi/hero/detail?player=${h.player_id}">Открыть игрока →</a>`;
  } else {
    $("lifeHeroDay").innerHTML = `<header><span>👑</span><div><small>ГЕРОЙ ДНЯ</small><strong>Пока определяется</strong></div></header>`;
  }

  const topRows = (items, emptyText) => items?.length
    ? items.slice(0,5).map((x, i) => `
        <div class="life-contributor-row">
          <span class="life-contributor-rank">${i + 1}</span>
          <div><a class="game-profile-link" href="https://playwekings.mobi/hero/detail?player=${x.player_id}">${escapeHtml(x.nickname)}</a>
          <small>${escapeHtml(x.organization)}</small></div>
          <b>+${fmt(x.gain)}</b>
        </div>`).join("")
    : `<p class="life-empty">${emptyText}</p>`;
  $("lifeContributorTops").innerHTML = `
    <div class="life-contributor-section">
      <header><span>🛡️</span><div><small>ТОП В БРАТСТВАХ</small><strong>Прирост характеристик</strong></div></header>
      ${topRows(data.top_brotherhood, "Пока нет прироста")}
    </div>
    <div class="life-contributor-section">
      <header><span>🏰</span><div><small>ТОП В КЛАНАХ</small><strong>Прирост характеристик</strong></div></header>
      ${topRows(data.top_clan, "Пока нет прироста")}
    </div>`;
}

function openLife(){$("lifePanel").classList.remove("hidden");$("lifeToggle").classList.add("active");$("lifeToggle").setAttribute("aria-expanded","true");if(!lifeState.loaded)loadLife().catch(()=>{$("lifeEvents").innerHTML='<p class="life-empty">Не удалось загрузить события.</p>';});loadLifeSummary().catch(()=>{});$("lifePanel").scrollIntoView({behavior:"smooth",block:"start"});}
function closeLife(){$("lifePanel").classList.add("hidden");$("lifeToggle").classList.remove("active");$("lifeToggle").setAttribute("aria-expanded","false");}


const todayTopsState = { loaded: false };
async function loadTodayTops(force = false) {
  if (todayTopsState.loaded && !force) return;
  $("todayTopsGrid").innerHTML = '<p class="life-empty">Считаем сегодняшние топы…</p>';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`/api/today-tops?_=${Date.now()}`, {
      cache: "no-store",
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
  if (!data.ready) {
    $("todayTopsDate").textContent = "Нужно минимум два снимка за сегодня";
    $("todayHero").innerHTML = "";
    $("todayTopsGrid").innerHTML = '<p class="life-empty">Пока недостаточно данных за сегодня.</p>';
    return;
  }
  const d = new Date(data.date + "T12:00:00");
  $("todayTopsDate").textContent = `Итоги за ${d.toLocaleDateString("ru-RU")}`;
  const hero = data.hero;
  $("todayHero").innerHTML = hero ? `
    <span>👑 Герой сегодняшнего дня</span>
    <a class="game-profile-link" href="https://playwekings.mobi/hero/detail?player=${hero.player_id}">${escapeHtml(hero.nickname)}</a>
    <b>${hero.first_places} ${hero.first_places === 1 ? "первое место" : "первых мест"}</b>` : "";
  $("todayTopsGrid").innerHTML = data.tops?.length ? data.tops.map(x => `
    <article class="yesterday-top-card">
      <span>${x.icon} ${escapeHtml(x.label)}</span>
      <a class="game-profile-link" href="https://playwekings.mobi/hero/detail?player=${x.player_id}">${escapeHtml(x.nickname)}</a>
      <b>+${fmt(x.gain)}</b>
    </article>`).join("") : '<p class="life-empty">За сегодня прироста по этим показателям нет.</p>';
    todayTopsState.loaded = true;
  } finally {
    clearTimeout(timer);
  }
}
function openTodayTops(){
  $("todayTopsPanel").classList.remove("hidden");
  $("todayTopsToggle").classList.add("active");
  $("todayTopsToggle").setAttribute("aria-expanded","true");
  loadTodayTops().catch(error=>{
    $("todayTopsGrid").innerHTML = `<p class="life-empty">Не удалось загрузить топы. ${error?.name === "AbortError" ? "Сервер отвечает слишком долго." : "Проверьте соединение или попробуйте ещё раз."}</p>`;
  });
  $("todayTopsPanel").scrollIntoView({behavior:"smooth",block:"start"});
}
function closeTodayTops(){
  $("todayTopsPanel").classList.add("hidden");
  $("todayTopsToggle").classList.remove("active");
  $("todayTopsToggle").setAttribute("aria-expanded","false");
}

const yesterdayTopsState = { loaded: false };
async function loadYesterdayTops(force = false) {
  if (yesterdayTopsState.loaded && !force) return;
  $("yesterdayTopsGrid").innerHTML = '<p class="life-empty">Считаем вчерашние топы…</p>';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`/api/yesterday-tops?_=${Date.now()}`, {
      cache: "no-store",
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
  if (!data.ready) {
    $("yesterdayTopsDate").textContent = "Нужно минимум три дневных снимка";
    $("yesterdayHero").innerHTML = "";
    $("yesterdayTopsGrid").innerHTML = '<p class="life-empty">Пока недостаточно данных.</p>';
    return;
  }
  const d = new Date(data.date + "T12:00:00");
  $("yesterdayTopsDate").textContent = `Итоги за ${d.toLocaleDateString("ru-RU")}`;
  const hero = data.hero;
  $("yesterdayHero").innerHTML = hero ? `
    <span>👑 Герой вчерашнего дня</span>
    <a class="game-profile-link" href="https://playwekings.mobi/hero/detail?player=${hero.player_id}">${escapeHtml(hero.nickname)}</a>
    <b>${hero.first_places} ${hero.first_places === 1 ? "первое место" : "первых места"}</b>` : "";
  $("yesterdayTopsGrid").innerHTML = data.tops?.length ? data.tops.map(x => `
    <article class="yesterday-top-card">
      <span>${x.icon} ${escapeHtml(x.label)}</span>
      <a class="game-profile-link" href="https://playwekings.mobi/hero/detail?player=${x.player_id}">${escapeHtml(x.nickname)}</a>
      <b>+${fmt(x.gain)}</b>
    </article>`).join("") : '<p class="life-empty">За вчера прироста по этим показателям нет.</p>';
    yesterdayTopsState.loaded = true;
  } finally {
    clearTimeout(timer);
  }
}
function openYesterdayTops(){
  $("yesterdayTopsPanel").classList.remove("hidden");
  $("yesterdayTopsToggle").classList.add("active");
  $("yesterdayTopsToggle").setAttribute("aria-expanded","true");
  loadYesterdayTops().catch(error=>{
    $("yesterdayTopsGrid").innerHTML = `<p class="life-empty">Не удалось загрузить топы. ${error?.name === "AbortError" ? "Сервер отвечает слишком долго." : "Проверьте соединение или попробуйте ещё раз."}</p>`;
  });
  $("yesterdayTopsPanel").scrollIntoView({behavior:"smooth",block:"start"});
}
function closeYesterdayTops(){
  $("yesterdayTopsPanel").classList.add("hidden");
  $("yesterdayTopsToggle").classList.remove("active");
  $("yesterdayTopsToggle").setAttribute("aria-expanded","false");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

document.querySelectorAll(".modes button[data-mode]").forEach(button => {
  button.onclick = () => {
    document.querySelectorAll(".modes button[data-mode]").forEach(item => item.classList.remove("active"));
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


if ($("lifeToggle") && $("lifePanel")) {
  $("lifeToggle").onclick=()=>{$("lifePanel").classList.contains("hidden")?openLife():closeLife();};
}
if ($("lifeClose")) $("lifeClose").onclick=closeLife;
$("todayTopsToggle").onclick=()=>{$("todayTopsPanel").classList.contains("hidden")?openTodayTops():closeTodayTops();};
$("todayTopsClose").onclick=closeTodayTops;
$("yesterdayTopsToggle").onclick=()=>{$("yesterdayTopsPanel").classList.contains("hidden")?openYesterdayTops():closeYesterdayTops();};
$("yesterdayTopsClose").onclick=closeYesterdayTops;
document.querySelectorAll("[data-life-period]").forEach(b=>{b.onclick=()=>loadLife(b.dataset.lifePeriod).catch(()=>{$("lifeEvents").innerHTML='<p class="life-empty">Не удалось загрузить события.</p>';});});

$("todayBadge").textContent = new Date().toLocaleDateString("ru-RU", {
  day: "2-digit", month: "short"
}).replace(".", "").toUpperCase();
syncMobileNav();
if ($("attackRefresh")) $("attackRefresh").onclick = refreshAttacks;
loadStatus().catch(() => {});
loadAttacks().catch(() => {});
loadPlayers().catch(() => $("rows").innerHTML = '<tr><td colspan="7" class="loading">Не удалось загрузить данные</td></tr>');
setInterval(() => loadStatus().catch(() => {}), 30000);
setInterval(() => loadAttacks().catch(() => {}), 60000);

/* V83 — cinematic Viking Arena: weapons, styles and special attacks */
const arenaState={players:[],a:null,b:null,hpA:100,hpB:100,timer:null,running:false,round:0,turn:'A',blockingA:false,blockingB:false,weaponA:'axe',weaponB:'axe',styleA:'berserker',styleB:'berserker'};
const arena$=id=>document.getElementById(id);
const arenaFmt=n=>Number(n||0).toLocaleString("ru-RU");
function arenaEscape(s){const d=document.createElement("div");d.textContent=s??"";return d.innerHTML;}
function arenaRating(p){const vals=[p.power,p.defense,p.agility,p.mastery,p.vitality].map(Number);return Math.round(vals.reduce((a,b)=>a+b,0)/5);}
function arenaFillSelects(){const opts=arenaState.players.map(p=>`<option value="${p.id}">${arenaEscape(p.nickname)} · ур. ${p.level??"—"} · ${arenaFmt(p.power)}</option>`).join("");arena$("arenaFighterA").innerHTML=opts;arena$("arenaFighterB").innerHTML=opts;if(arenaState.players.length>1){arena$("arenaFighterA").value=arenaState.players[0].id;arena$("arenaFighterB").value=arenaState.players[1].id;}arenaSyncFighters();}
function arenaFind(id){return arenaState.players.find(p=>String(p.id)===String(id));}
function arenaStyleFor(p){const vals={berserker:Number(p.power||0),shield:Number(p.defense||0),hunter:Number(p.agility||0),jarl:Number(p.mastery||0)+Number(p.vitality||0)*.35};return Object.keys(vals).sort((a,b)=>vals[b]-vals[a])[0];}
function arenaWeaponFor(p){const vals={axe:Number(p.power||0),sword:Number(p.mastery||0),spear:Number(p.agility||0)};return Object.keys(vals).sort((a,b)=>vals[b]-vals[a])[0];}
function arenaSpecial(p){const power=Number(p.power||0),def=Number(p.defense||0),agi=Number(p.agility||0),mastery=Number(p.mastery||0),vit=Number(p.vitality||0);const vals={"Ярость Берсерка":power*1.25+vit*.3,"Сокрушение щитом":def*1.25+power*.2,"Охотничий выпад":agi*1.25+mastery*.35,"Удар в уязвимое место":mastery*1.35+agi*.25};return Object.keys(vals).sort((a,b)=>vals[b]-vals[a])[0];}
function arenaVikingSVG(side){
  const red=side==='B',uid=red?'r':'b';
  const weapon=arenaState['weapon'+side]||'axe', style=arenaState['style'+side]||'berserker';
  const armor=style==='berserker'?'#4a2924':style==='shield'?'#26394a':style==='hunter'?'#354a31':'#3b303f';
  const accent=red?'#8f3834':'#345b7c';
  const weaponSvg=weapon==='sword'
    ? `<g class="v-weapon v-sword"><path d="M180 168 L230 78" stroke="#3a281c" stroke-width="10" stroke-linecap="round"/><path d="M224 87 L241 52" stroke="#dfe4df" stroke-width="8" stroke-linecap="round"/><path d="M217 98 L232 105" stroke="#d7b24e" stroke-width="5"/><path d="M211 109 L227 116" stroke="#d7b24e" stroke-width="5"/></g>`
    : weapon==='spear'
    ? `<g class="v-weapon v-spear"><path d="M184 181 L232 65" stroke="#5b3a21" stroke-width="9"/><path d="M226 70 L244 39 L235 78Z" fill="#e2e5df" stroke="#222" stroke-width="4"/></g>`
    : `<g class="v-weapon v-axe"><path d="M180 169 L230 103" stroke="#3a2519" stroke-width="12" stroke-linecap="round"/><path d="M223 105 Q243 96 238 129 Q232 150 210 151 Q221 130 223 105Z" fill="url(#${uid}metal)" stroke="#222627" stroke-width="5"/></g>`;
  return `<svg class="viking-svg ${red?'viking-red':'viking-blue'} style-${style} weapon-${weapon}" viewBox="0 0 240 360" role="img" aria-label="Викинг">
    <defs>
      <linearGradient id="${uid}skin" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e4ad78"/><stop offset=".55" stop-color="#a8643e"/><stop offset="1" stop-color="#6f3b29"/></linearGradient>
      <linearGradient id="${uid}hair" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#d2aa70"/><stop offset=".5" stop-color="#82512f"/><stop offset="1" stop-color="#3c241b"/></linearGradient>
      <linearGradient id="${uid}fur" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${armor}"/><stop offset=".55" stop-color="#211c1b"/><stop offset="1" stop-color="#101010"/></linearGradient>
      <linearGradient id="${uid}metal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#eef0eb"/><stop offset=".35" stop-color="#929890"/><stop offset=".65" stop-color="#444a49"/><stop offset="1" stop-color="#1e2425"/></linearGradient>
      <radialGradient id="${uid}shield"><stop stop-color="#d7b35a"/><stop offset=".12" stop-color="#513a25"/><stop offset=".17" stop-color="${accent}"/><stop offset=".72" stop-color="${red?'#2d1718':'#202c3b'}"/><stop offset=".82" stop-color="#b17c30"/><stop offset="1" stop-color="#1b1512"/></radialGradient>
      <filter id="${uid}shadow"><feDropShadow dx="0" dy="8" stdDeviation="7" flood-opacity=".65"/></filter>
    </defs>
    <ellipse class="v-shadow" cx="120" cy="345" rx="68" ry="13"/>
    <g class="viking-rig" filter="url(#${uid}shadow)">
      <g class="v-legs"><path d="M88 225 L78 322 Q77 334 88 337 L108 337 L121 250 Z" fill="#252321" stroke="#171313" stroke-width="7"/><path d="M119 248 L135 337 L158 337 Q166 330 160 320 L149 224 Z" fill="#171717" stroke="#171313" stroke-width="7"/><path d="M75 330 Q92 322 111 331 L111 345 L68 345 Q64 338 75 330Z" fill="#17100e"/><path d="M132 331 Q151 323 166 331 L175 345 L129 345 Q125 338 132 331Z" fill="#17100e"/></g>
      <g class="v-body"><path d="M73 103 Q119 82 167 106 L176 222 Q148 244 93 226 L64 207 Z" fill="url(#${uid}fur)" stroke="#17120f" stroke-width="8"/><path d="M91 119 Q120 105 151 119 L151 211 Q121 222 91 209Z" fill="none" stroke="#a07b43" stroke-width="4" opacity=".8"/><path d="M82 151 L157 181 M78 177 L157 207" stroke="#9a7a4b" stroke-width="3" opacity=".45"/><path d="M94 112 Q119 128 151 112" fill="none" stroke="#d0ad68" stroke-width="5" opacity=".65"/></g>
      <g class="v-arm v-arm-back"><path d="M79 120 Q55 144 48 182" fill="none" stroke="#241812" stroke-width="27" stroke-linecap="round"/><path d="M79 120 Q55 144 48 182" fill="none" stroke="url(#${uid}skin)" stroke-width="17" stroke-linecap="round"/></g>
      <g class="v-arm v-arm-front"><path d="M158 116 Q180 138 187 173" fill="none" stroke="#241812" stroke-width="28" stroke-linecap="round"/><path d="M158 116 Q180 138 187 173" fill="none" stroke="url(#${uid}skin)" stroke-width="18" stroke-linecap="round"/></g>
      <g class="v-shield"><circle cx="177" cy="179" r="47" fill="url(#${uid}shield)" stroke="#17120f" stroke-width="7"/><circle cx="177" cy="179" r="10" fill="#d4b35b" stroke="#342617" stroke-width="4"/><path d="M177 133 L177 225 M131 179 L223 179" stroke="#c0913d" stroke-width="3" opacity=".7"/></g>
      ${weaponSvg}
      <g class="v-head"><path d="M83 71 Q82 28 120 17 Q160 25 160 72 L151 110 Q119 129 88 107Z" fill="url(#${uid}skin)" stroke="#241711" stroke-width="7"/><path class="v-hair" d="M73 72 Q65 24 101 10 Q130 -3 158 19 Q180 37 165 83 L151 68 Q145 35 120 30 Q94 34 91 75Z" fill="url(#${uid}hair)" stroke="#291a14" stroke-width="7"/><path d="M83 53 Q67 31 53 43 Q69 59 87 66Z" fill="#d7d8cf" stroke="#282725" stroke-width="5"/><path d="M157 53 Q175 31 189 43 Q171 59 155 66Z" fill="#d7d8cf" stroke="#282725" stroke-width="5"/><ellipse cx="105" cy="71" rx="6" ry="8" fill="#16120f"/><ellipse cx="138" cy="71" rx="6" ry="8" fill="#16120f"/><path d="M111 91 Q121 97 132 90" fill="none" stroke="#5a2d22" stroke-width="5" stroke-linecap="round"/><path d="M96 96 Q119 129 146 97 L149 119 Q121 144 93 119Z" fill="url(#${uid}hair)" stroke="#291a14" stroke-width="5"/></g>
      <path class="v-belt" d="M75 201 Q121 218 167 202" fill="none" stroke="#b98a43" stroke-width="10"/><circle cx="120" cy="211" r="8" fill="#e1c06c" stroke="#49341e" stroke-width="3"/>
    </g>
  </svg>`;
}
function arenaRenderFighters(){arena$("fighterA").innerHTML=arenaVikingSVG('A');arena$("fighterB").innerHTML=arenaVikingSVG('B');}
function arenaSyncFighters(){
  arenaState.a=arenaFind(arena$("arenaFighterA").value);arenaState.b=arenaFind(arena$("arenaFighterB").value);if(!arenaState.a||!arenaState.b)return;
  arenaState.weaponA=arenaWeaponFor(arenaState.a);arenaState.weaponB=arenaWeaponFor(arenaState.b);arenaState.styleA=arenaStyleFor(arenaState.a);arenaState.styleB=arenaStyleFor(arenaState.b);
  arena$("arenaWeaponA").value=arenaState.weaponA;arena$("arenaWeaponB").value=arenaState.weaponB;arena$("arenaStyleA").value=arenaState.styleA;arena$("arenaStyleB").value=arenaState.styleB;
  const a=arenaState.a,b=arenaState.b;arenaRenderFighters();arena$("arenaNameA").textContent=a.nickname;arena$("arenaNameB").textContent=b.nickname;arena$("arenaLevelA").textContent=`ур. ${a.level??"—"}`;arena$("arenaLevelB").textContent=`ур. ${b.level??"—"}`;arena$("arenaHpNameA").textContent=a.nickname;arena$("arenaHpNameB").textContent=b.nickname;arena$("arenaCardNameA").textContent=a.nickname;arena$("arenaCardNameB").textContent=b.nickname;arena$("arenaRatingA").textContent=`Рейтинг ${arenaFmt(arenaRating(a))}`;arena$("arenaRatingB").textContent=`Рейтинг ${arenaFmt(arenaRating(b))}`;
  const stats=p=>`<span>⚡ <b>${arenaFmt(p.power)}</b><small>Сила</small></span><span>🛡️ <b>${arenaFmt(p.defense)}</b><small>Защита</small></span><span>🌀 <b>${arenaFmt(p.agility)}</b><small>Ловкость</small></span><span>🎯 <b>${arenaFmt(p.mastery)}</b><small>Мастерство</small></span><span>❤️ <b>${arenaFmt(p.vitality)}</b><small>Живучесть</small></span><span>🔥 <b>${arenaEscape(arenaSpecial(p))}</b><small>Лучший спецприём</small></span>`;
  arena$("arenaStatsA").innerHTML=stats(a);arena$("arenaStatsB").innerHTML=stats(b);arenaResetStage();
}
function arenaResetStage(){clearTimeout(arenaState.timer);arenaState.running=false;arenaState.round=0;arenaState.turn='A';arenaState.blockingA=false;arenaState.blockingB=false;["fighterA","fighterB"].forEach(id=>arena$(id).classList.remove("attacking","hit","critical","dodging","ko","jumping","blocking","winner"));arena$("arenaHpA").style.width="100%";arena$("arenaHpB").style.width="100%";arena$("arenaHpTextA").textContent="100 / 100";arena$("arenaHpTextB").textContent="100 / 100";arena$("arenaRound").textContent="ПОДГОТОВКА";arena$("arenaCommentary").textContent="Выберите приём или нажмите «Начать бой»";arena$("arenaLog").innerHTML='<div class="arena-log-title">ЖУРНАЛ БОЯ</div><p>Бой ещё не начался.</p>';arena$("arenaResult").classList.add("hidden");}
function arenaWrite(text){const p=document.createElement("p");p.innerHTML=text;arena$("arenaLog").appendChild(p);arena$("arenaLog").scrollTop=arena$("arenaLog").scrollHeight;}
function arenaStatScore(p){return Number(p.power)*.36+Number(p.mastery)*.22+Number(p.agility)*.16+Number(p.defense)*.14+Number(p.vitality)*.12;}
function arenaDamage(attacker,defender,type){
  const ar=arenaStatScore(attacker),dr=arenaStatScore(defender),ratio=ar/(ar+dr||1),weapon=attacker===arenaState.a?arenaState.weaponA:arenaState.weaponB,style=attacker===arenaState.a?arenaState.styleA:arenaState.styleB;
  const variance=.82+Math.random()*.36;let base=5.5+ratio*8+Number(attacker.power)/(Number(attacker.power)+Number(defender.defense)+1)*5;
  const weaponMod={axe:1.08,sword:1.0,spear:.94}[weapon],styleMod={berserker:1.12,shield:.98,hunter:1.02,jarl:1.05}[style];
  if(type==='quick')base*=.82;if(type==='heavy')base*=1.35;if(type==='special')base*=1.58;
  if(type==='block')return{damage:0,blocked:true};
  const crit=Math.random()<Math.min(.32,.07+Number(attacker.mastery)/(Number(attacker.mastery)+Number(defender.mastery)+1)*.2+(type==='special'?.08:0));
  const dodge=Math.random()<Math.min(.25,.025+Number(defender.agility)/(Number(defender.agility)+Number(attacker.mastery)+1)*.18-(type==='heavy'?.04:0));
  if(dodge)return{damage:0,critical:false,dodge:true};
  let damage=base*weaponMod*styleMod*variance*(crit?1.7:1);
  const special=type==='special'?arenaSpecial(attacker):null;
  return{damage:Math.max(2,Math.round(damage)),critical:crit,dodge:false,special};
}
function arenaAnimate(id,cls){const el=arena$(id);el.classList.remove("attacking","hit","critical","dodging","jumping","blocking","winner");void el.offsetWidth;el.classList.add(cls);setTimeout(()=>el.classList.remove("attacking","hit","critical","dodging","jumping","blocking"),900);}
function arenaSetHp(side,hp){const safe=Math.max(0,Math.min(100,hp));arenaState[side]=safe;const id=side==="hpA"?"A":"B";arena$("arenaHp"+id).style.width=safe+"%";arena$("arenaHpText"+id).textContent=`${Math.round(safe)} / 100`;}
function arenaStrike(attackerSide,type='quick'){
  if(!arenaState.running)return;const attacker=attackerSide==='A'?arenaState.a:arenaState.b,defender=attackerSide==='A'?arenaState.b:arenaState.a,targetSide=attackerSide==='A'?'B':'A',targetHp=attackerSide==='A'?arenaState.hpB:arenaState.hpA;
  arena$("arenaRound").textContent=`РАУНД ${arenaState.round}`;arenaAnimate("fighter"+attackerSide,type==='block'?"blocking":"attacking");if(type==='heavy'||type==='special'){const el=arena$("fighter"+attackerSide);el.classList.add("jumping");setTimeout(()=>el.classList.remove("jumping"),900);}
  setTimeout(()=>{
    const result=arenaDamage(attacker,defender,type),targetId="fighter"+targetSide;
    if(result.blocked){arenaWrite(`<b>${arenaEscape(attacker.nickname)}</b> приготовился к защите.`);arena$("arenaCommentary").textContent=`🛡️ ${attacker.nickname}: ЗАЩИТА`;return;}
    if(result.dodge){arenaAnimate(targetId,"dodging");arenaWrite(`<b>${arenaEscape(defender.nickname)}</b> уклонился от атаки <b>${arenaEscape(attacker.nickname)}</b>!`);arena$("arenaCommentary").textContent=`💨 ${defender.nickname} УКЛОНИЛСЯ!`;return;}
    arenaAnimate(targetId,result.critical?"critical":"hit");const flash=arena$("arenaHitFlash");flash.classList.remove("show");void flash.offsetWidth;flash.classList.add("show");const next=targetHp-result.damage;targetSide==='A'?arenaSetHp('hpA',next):arenaSetHp('hpB',next);
    const verb=result.special?result.special.toUpperCase():(result.critical?'КРИТИЧЕСКИЙ УДАР':type==='heavy'?'ТЯЖЁЛЫЙ УДАР':'УДАР');arena$("arenaCommentary").textContent=`${result.critical?'💥':'⚔️'} ${attacker.nickname}: ${verb} −${result.damage} HP`;arenaWrite(`<b>${arenaEscape(attacker.nickname)}</b> — ${arenaEscape(verb.toLowerCase())} <strong>−${result.damage}</strong> HP`);if(next<=0)arenaFinish(attackerSide);
  },type==='special'?470:360);
}
function arenaFinish(winnerSide){arenaState.running=false;clearTimeout(arenaState.timer);const loserSide=winnerSide==='A'?'B':'A';arena$("fighter"+loserSide).classList.add("ko");arena$("fighter"+winnerSide).classList.add("winner");const winner=winnerSide==='A'?arenaState.a:arenaState.b,loser=winnerSide==='A'?arenaState.b:arenaState.a;arena$("arenaRound").textContent="НОКАУТ";arena$("arenaCommentary").textContent=`🏆 ${winner.nickname} ПОБЕЖДАЕТ!`;arenaWrite(`<strong>🏆 ${arenaEscape(winner.nickname)} побеждает ${arenaEscape(loser.nickname)}!</strong>`);arena$("arenaResultTitle").textContent=`🏆 ${winner.nickname.toUpperCase()} ПОБЕЖДАЕТ`;arena$("arenaResultText").textContent=`Нокаут в ${arenaState.round}-м раунде · спецприём: ${arenaSpecial(winner)} · рейтинг ${arenaFmt(arenaRating(winner))}`;arena$("arenaResult").classList.remove("hidden");}
function arenaRoundStep(){if(!arenaState.running)return;arenaState.round++;const side=arenaState.turn;arenaState.turn=side==='A'?'B':'A';const roll=Math.random();const type=roll<.16?'special':roll<.36?'heavy':'quick';arenaStrike(side,type);arenaState.timer=setTimeout(arenaRoundStep,type==='special'?1350:1050);}
async function openArena(){arena$("arenaPanel").classList.remove("hidden");arena$("arenaToggle").setAttribute("aria-expanded","true");if(!arenaState.players.length){arena$("arenaCommentary").textContent="Загрузка бойцов из статистики…";try{const r=await fetch(`/api/arena/players?_=${Date.now()}`,{cache:"no-store"});const data=await r.json();arenaState.players=data.players||[];arenaFillSelects();}catch(e){arena$("arenaCommentary").textContent="Не удалось загрузить игроков.";}}else arenaSyncFighters();arena$("arenaPanel").scrollIntoView({behavior:"smooth",block:"start"});}
function closeArena(){clearTimeout(arenaState.timer);arenaState.running=false;arena$("arenaPanel").classList.add("hidden");arena$("arenaToggle").setAttribute("aria-expanded","false");}
function startArena(){if(!arenaState.a||!arenaState.b||arenaState.a.id===arenaState.b.id){arena$("arenaCommentary").textContent="Нужно выбрать двух разных викингов.";return;}arenaResetStage();arenaState.running=true;arena$("arenaCommentary").textContent="🔥 БОЙ НАЧИНАЕТСЯ!";arena$("arenaLog").innerHTML='<div class="arena-log-title">ЖУРНАЛ БОЯ</div><p>⚔️ Арена открыта!</p>';setTimeout(arenaRoundStep,700);}
function arenaManualAction(type){if(!arenaState.running)return;const side=arenaState.turn;arenaState.turn=side==='A'?'B':'A';arenaState.round++;arenaStrike(side,type);}
arena$("arenaToggle")?.addEventListener("click",openArena);arena$("arenaClose")?.addEventListener("click",closeArena);arena$("arenaStart")?.addEventListener("click",startArena);arena$("arenaAgain")?.addEventListener("click",startArena);arena$("arenaFighterA")?.addEventListener("change",arenaSyncFighters);arena$("arenaFighterB")?.addEventListener("change",arenaSyncFighters);arena$("arenaSwap")?.addEventListener("click",()=>{const a=arena$("arenaFighterA").value;arena$("arenaFighterA").value=arena$("arenaFighterB").value;arena$("arenaFighterB").value=a;arenaSyncFighters();});
["A","B"].forEach(side=>{arena$("arenaWeapon"+side)?.addEventListener("change",e=>{arenaState["weapon"+side]=e.target.value;arenaRenderFighters();});arena$("arenaStyle"+side)?.addEventListener("change",e=>{arenaState["style"+side]=e.target.value;arenaRenderFighters();});});
document.querySelectorAll("[data-arena-action]").forEach(btn=>btn.addEventListener("click",()=>arenaManualAction(btn.dataset.arenaAction)));
