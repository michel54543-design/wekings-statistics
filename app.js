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

async function loadAttacks() {
  const box = $("attackSchedule");
  try {
    const response = await fetch(`/api/attacks?_=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    $("dragonTime").textContent = attackTimeText(data.dragon_at, 60);
    $("serpentTime").textContent = attackTimeText(data.serpent_at, 90);
    $("weatherTime").textContent = weatherTimeText(data.weather_at);
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


const todayTopsState = { loaded: false, loading: false };
async function loadTodayTops(force = false) {
  if (todayTopsState.loading) return;
  if (todayTopsState.loaded && !force) return;
  todayTopsState.loading = true;
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
    todayTopsState.loading = false;
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

const yesterdayTopsState = { loaded: false, loading: false };
async function loadYesterdayTops(force = false) {
  if (yesterdayTopsState.loading) return;
  if (yesterdayTopsState.loaded && !force) return;
  yesterdayTopsState.loading = true;
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
    yesterdayTopsState.loading = false;
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


$("lifeToggle").onclick=()=>{$("lifePanel").classList.contains("hidden")?openLife():closeLife();};
$("lifeClose").onclick=closeLife;
$("todayTopsToggle").onclick=()=>{$("todayTopsPanel").classList.contains("hidden")?openTodayTops():closeTodayTops();};
$("todayTopsClose").onclick=closeTodayTops;
$("yesterdayTopsToggle").onclick=()=>{$("yesterdayTopsPanel").classList.contains("hidden")?openYesterdayTops():closeYesterdayTops();};
$("yesterdayTopsClose").onclick=closeYesterdayTops;
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


/* V85 — isolated Viking Arena. Does not alter the site's existing statistics logic. */
(() => {
  const $a = id => document.getElementById(id);
  if (!$a('arenaPanel')) return;
  const st = { players: [], a: null, b: null, hpA: 100, hpB: 100, timer: null, running: false, round: 0, queued: {A:null,B:null} };
  const esc = s => { const d=document.createElement('div'); d.textContent=s ?? ''; return d.innerHTML; };
  const num = n => Number(n || 0);
  const fmt = n => num(n).toLocaleString('ru-RU');
  const weaponFor = p => {
    const power=num(p.power), agi=num(p.agility), mast=num(p.mastery);
    if (power >= agi*1.15 && power >= mast*1.15) return ['axe','🪓 Боевой топор'];
    if (agi >= mast*1.10) return ['spear','🔱 Копьё'];
    return ['sword','⚔ Меч'];
  };
  const styleFor = p => {
    const power=num(p.power), def=num(p.defense), agi=num(p.agility), vit=num(p.vitality);
    if (power+vit > def+agi*1.35) return ['berserker','Берсерк'];
    if (def >= power*1.08) return ['shield','Щитоносец'];
    if (agi >= def*1.12) return ['hunter','Охотник'];
    return ['jarl','Ярл'];
  };
  const rating = p => Math.round((num(p.power)+num(p.defense)+num(p.agility)+num(p.mastery)+num(p.vitality))/5);
  const statScore = p => num(p.power)*.36+num(p.mastery)*.22+num(p.agility)*.16+num(p.defense)*.14+num(p.vitality)*.12;

  function weaponSvg(type) {
    if(type==='sword') return `<g class="vk-weapon vk-sword"><path d="M213 218 L280 91"/><path d="M204 224 L225 234" class="vk-grip"/><path d="M277 88 L291 62 L267 76 Z" class="vk-blade"/></g>`;
    if(type==='spear') return `<g class="vk-weapon vk-spear"><path d="M210 224 L293 58"/><path d="M293 58 L308 31 L286 46 Z" class="vk-blade"/></g>`;
    return `<g class="vk-weapon vk-axe"><path d="M210 224 L271 102"/><path d="M256 115 Q286 91 305 119 L291 153 Q273 137 256 115 Z" class="vk-blade"/></g>`;
  }
  function vikingSvg(side,p){
    const red=side==='B', [weapon]=weaponFor(p), [style]=styleFor(p);
    const armor=red?'#5a211c':'#233644', fur=red?'#3b231c':'#332a20', metal='#9a9a92', skin='#a96f4c', skin2='#c48a61', hair=red?'#17100c':'#251913';
    const accent=style==='jarl'?'#d3a743':style==='shield'?'#648aa5':style==='hunter'?'#708d5c':'#a44734';
    return `<svg class="viking-svg ${red?'red':''} weapon-${weapon} style-${style}" viewBox="0 0 360 480" preserveAspectRatio="xMidYMax meet" aria-label="Викинг">
      <defs><linearGradient id="armor${side}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${armor}"/><stop offset="1" stop-color="#111820"/></linearGradient><filter id="shadow${side}"><feDropShadow dx="0" dy="10" stdDeviation="7" flood-opacity=".55"/></filter></defs>
      <ellipse class="vk-shadow" cx="180" cy="458" rx="100" ry="16"/>
      <g class="vk-rig" filter="url(#shadow${side})">
        <g class="vk-legs"><path d="M143 326 L117 430 L146 439 L176 348" fill="#171a1d" stroke="#0b0c0d" stroke-width="8"/><path d="M190 347 L207 431 L238 428 L214 321" fill="#171a1d" stroke="#0b0c0d" stroke-width="8"/><path d="M112 428 Q134 420 151 437 L151 451 L102 451Z" fill="#3b261d"/><path d="M202 428 Q223 419 242 433 L245 450 L198 450Z" fill="#3b261d"/></g>
        <g class="vk-body"><path d="M118 173 Q177 143 226 178 L235 309 Q177 340 108 306Z" fill="url(#armor${side})" stroke="#0d1012" stroke-width="9"/><path d="M121 184 Q177 208 224 184" fill="none" stroke="${accent}" stroke-width="7"/><path d="M112 270 Q176 294 232 269" fill="none" stroke="${fur}" stroke-width="18"/><path d="M122 210 L224 298" stroke="#70532d" stroke-width="5" opacity=".8"/><path d="M219 211 L127 294" stroke="#70532d" stroke-width="5" opacity=".8"/></g>
        <g class="vk-head"><path d="M116 105 Q118 50 177 43 Q231 50 235 107 L217 170 Q176 192 135 166Z" fill="${skin}" stroke="#17100c" stroke-width="8"/><path d="M120 105 Q125 37 178 34 Q225 39 232 105 L213 89 Q178 72 132 90Z" fill="${hair}"/><path d="M126 103 Q176 80 228 102 L217 127 Q177 109 134 127Z" fill="#181716"/><path d="M134 134 Q177 169 218 133 Q208 182 177 184 Q145 181 134 134Z" fill="#2c1c16"/><path d="M146 120 Q154 114 162 120 M186 120 Q194 114 202 120" fill="none" stroke="#1a110d" stroke-width="5" stroke-linecap="round"/><path d="M164 138 Q177 145 190 137" fill="none" stroke="#714632" stroke-width="4"/><path d="M122 76 L176 47 L231 76 L218 102 L176 84 L135 103Z" fill="${metal}" stroke="#151617" stroke-width="6"/><path d="M119 78 L98 113 L127 121 L140 95Z" fill="#686b68" stroke="#151617" stroke-width="5"/><path d="M233 78 L254 113 L225 121 L212 95Z" fill="#686b68" stroke="#151617" stroke-width="5"/><circle cx="177" cy="54" r="8" fill="${accent}"/></g>
        <g class="vk-arm-back"><path d="M117 184 Q88 208 87 271 L110 278 Q123 232 145 208Z" fill="${skin2}" stroke="#151515" stroke-width="8"/><path d="M84 263 Q101 257 115 273 L108 299 Q90 296 80 281Z" fill="${fur}"/></g>
        <g class="vk-arm-front"><path d="M223 184 Q252 207 256 264 L231 272 Q216 231 195 207Z" fill="${skin2}" stroke="#151515" stroke-width="8"/><circle cx="249" cy="269" r="15" fill="${skin}" stroke="#151515" stroke-width="6"/>${weaponSvg(weapon)}</g>
        <g class="vk-shield"><path d="M92 215 Q48 231 56 293 Q65 338 99 354 Q134 335 143 291 Q150 233 92 215Z" fill="#2c3438" stroke="#c39a4c" stroke-width="8"/><path d="M92 224 L92 345 M60 285 L126 285" stroke="${accent}" stroke-width="5"/><circle cx="92" cy="285" r="12" fill="#d2ad61" stroke="#6e532b" stroke-width="4"/></g>
      </g></svg>`;
  }
  function render(){
    if(!$a('fighterA')) return;
    $a('fighterA').innerHTML=vikingSvg('A',st.a||{}); $a('fighterB').innerHTML=vikingSvg('B',st.b||{});
  }
  function find(id){return st.players.find(p=>String(p.id)===String(id));}
  function sync(){
    st.a=find($a('arenaFighterA').value); st.b=find($a('arenaFighterB').value); if(!st.a||!st.b) return;
    const a=st.a,b=st.b, wa=weaponFor(a), wb=weaponFor(b), sa=styleFor(a), sb=styleFor(b);
    [['arenaNameA',a.nickname],['arenaHpNameA',a.nickname],['arenaCardNameA',a.nickname],['arenaNameB',b.nickname],['arenaHpNameB',b.nickname],['arenaCardNameB',b.nickname]].forEach(([id,v])=>$a(id).textContent=v);
    $a('arenaLevelA').textContent=`ур. ${a.level??'—'}`; $a('arenaLevelB').textContent=`ур. ${b.level??'—'}`;
    $a('arenaLoadoutA').textContent=wa[1]; $a('arenaStyleA').textContent=sa[1]; $a('arenaLoadoutB').textContent=wb[1]; $a('arenaStyleB').textContent=sb[1];
    $a('arenaRatingA').textContent=`Рейтинг ${fmt(rating(a))}`; $a('arenaRatingB').textContent=`Рейтинг ${fmt(rating(b))}`;
    const stats=p=>`<span>⚡ <b>${fmt(p.power)}</b><small>Сила</small></span><span>🛡️ <b>${fmt(p.defense)}</b><small>Защита</small></span><span>🌀 <b>${fmt(p.agility)}</b><small>Ловкость</small></span><span>🎯 <b>${fmt(p.mastery)}</b><small>Мастерство</small></span><span>❤️ <b>${fmt(p.vitality)}</b><small>Живучесть</small></span>`;
    $a('arenaStatsA').innerHTML=stats(a); $a('arenaStatsB').innerHTML=stats(b); render(); reset();
  }
  function reset(){ clearTimeout(st.timer); st.running=false; st.round=0; st.hpA=100; st.hpB=100; st.queued={A:null,B:null}; ['fighterA','fighterB'].forEach(id=>$a(id).classList.remove('attacking','jumping','blocking','hit','critical','dodging','ko','winner','loser')); setHp('A',100);setHp('B',100);$a('arenaRound').textContent='БОЙ 1';$a('arenaCommentary').textContent='Викинги готовы. Оружие и стиль выбраны автоматически.';$a('arenaResult').classList.add('hidden');$a('arenaLog').innerHTML='<div class="arena-log-title">ЖУРНАЛ БОЯ</div><p>Бой ещё не начался.</p>'; }
  function setHp(side,hp){const safe=Math.max(0,Math.min(100,hp)); st[side==='A'?'hpA':'hpB']=safe; $a('arenaHp'+side).style.width=safe+'%';$a('arenaHpText'+side).textContent=`${Math.round(safe)} / 100`;}
  function actionName(a){return ({quick:'Быстрый удар',heavy:'Тяжёлый удар',block:'Защита',special:'Спецприём'})[a]||'Удар';}
  function actionFor(p, forced){if(forced) return forced; const r=Math.random(); if(r<.16)return'block'; if(r<.38)return'heavy'; if(r<.52)return'special'; return'quick';}
  function damage(attacker,defender,opt){
    const ar=statScore(attacker),dr=statScore(defender),ratio=ar/(ar+dr||1), [weapon]=weaponFor(attacker), [style]=styleFor(attacker);
    const wm={axe:1.18,sword:1.0,spear:.94}[weapon], sm={berserker:1.13,shield:.95,hunter:1.04,jarl:1.08}[style], am={quick:.9,heavy:1.34,block:.25,special:1.58}[opt.action];
    const dodge=Math.random()<Math.min(.24,.025+num(defender.agility)/(num(defender.agility)+num(attacker.mastery)+1)*.17); if(dodge)return{damage:0,dodge:true,critical:false};
    const crit=Math.random()<Math.min(.32,.06+num(attacker.mastery)/(num(attacker.mastery)+num(defender.mastery)+1)*.24);
    let d=(6+ratio*12)*(.84+Math.random()*.34)*wm*sm*am; if(opt.action==='special')d*=1+Math.min(.35,num(attacker.mastery)/(num(attacker.mastery)+12000)*.35); if(crit)d*=1.6;
    return{damage:Math.max(3,Math.round(d)),dodge:false,critical:crit};
  }
  function anim(id,cls){const e=$a(id);e.classList.remove('attacking','jumping','blocking','hit','critical','dodging');void e.offsetWidth;e.classList.add(cls);}
  function strike(side,forced){
    const attacker=side==='A'?st.a:st.b, defender=side==='A'?st.b:st.a, target=side==='A'?'B':'A'; const action=actionFor(attacker,forced); const [weapon]=weaponFor(attacker); const [style]=styleFor(attacker); const el=$a('fighter'+side);
    el.classList.remove('attacking','jumping','blocking'); void el.offsetWidth; if(action==='block')el.classList.add('blocking'); else el.classList.add(action==='special'||action==='heavy'?'jumping':'attacking');
    const delay=action==='special'||action==='heavy'?470:360;
    setTimeout(()=>{if(!st.running)return;const res=damage(attacker,defender,{action,weapon,style});
      if(res.dodge){anim('fighter'+target,'dodging');$a('arenaCommentary').textContent=`💨 ${defender.nickname} уклонился!`;write(`<b>${esc(defender.nickname)}</b> уклонился от атаки.`);return;}
      anim('fighter'+target,res.critical?'critical':'hit');const flash=$a('arenaHitFlash');flash.classList.remove('show');void flash.offsetWidth;flash.classList.add('show');
      const current=target==='A'?st.hpA:st.hpB,next=current-res.damage;setHp(target,next);$a('arenaCommentary').textContent=`${res.critical?'💥':'⚔️'} ${attacker.nickname}: ${res.critical?'КРИТИЧЕСКИЙ УДАР':'УДАР'} −${res.damage} HP`;write(`<b>${esc(attacker.nickname)}</b> — ${actionName(action).toLowerCase()} (${weapon==='axe'?'топор':weapon==='sword'?'меч':'копьё'}, ${style}) <strong>−${res.damage}</strong> HP${res.critical?' 🔥':''}`);if(next<=0)finish(side);
    },delay);
  }
  function write(t){const p=document.createElement('p');p.innerHTML=t;$a('arenaLog').appendChild(p);$a('arenaLog').scrollTop=$a('arenaLog').scrollHeight;}
  function finish(side){st.running=false;clearTimeout(st.timer);const win=side==='A'?st.a:st.b, lose=side==='A'?st.b:st.a; $a('fighter'+(side==='A'?'B':'A')).classList.add('ko','loser');$a('fighter'+side).classList.add('winner');$a('arenaRound').textContent='НОКАУТ';$a('arenaCommentary').textContent=`🏆 ${win.nickname} ПОБЕЖДАЕТ!`;write(`<strong>🏆 ${esc(win.nickname)} побеждает ${esc(lose.nickname)}!</strong>`);$a('arenaResultTitle').textContent=`🏆 ${win.nickname.toUpperCase()} ПОБЕЖДАЕТ`; $a('arenaResultText').textContent=`Нокаут в ${st.round}-м раунде · оружие: ${weaponFor(win)[1]} · стиль: ${styleFor(win)[1]}`;$a('arenaResult').classList.remove('hidden');}
  function roundStep(){if(!st.running)return;st.round++;$a('arenaRound').textContent=`РАУНД ${st.round}`;const side=st.round%2?'A':'B';strike(side,st.queued[side]);st.queued[side]=null;st.timer=setTimeout(roundStep,1150);}
  async function open(){ $a('arenaPanel').classList.remove('hidden');$a('arenaToggle').setAttribute('aria-expanded','true'); if(!st.players.length){$a('arenaCommentary').textContent='Загрузка бойцов из статистики…';try{const r=await fetch(`/api/arena/players?_=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const d=await r.json();st.players=d.players||[];const opts=st.players.map(p=>`<option value="${p.id}">${esc(p.nickname)} · ур. ${p.level??'—'} · ${fmt(p.power)}</option>`).join('');$a('arenaFighterA').innerHTML=opts;$a('arenaFighterB').innerHTML=opts;if(st.players.length>1){$a('arenaFighterA').value=st.players[0].id;$a('arenaFighterB').value=st.players[1].id;}sync();}catch(e){console.error(e);$a('arenaCommentary').textContent='Не удалось загрузить бойцов.';}} else sync();$a('arenaPanel').scrollIntoView({behavior:'smooth',block:'start'}); }
  function close(){clearTimeout(st.timer);st.running=false;$a('arenaPanel').classList.add('hidden');$a('arenaToggle').setAttribute('aria-expanded','false');}
  function start(){if(!st.a||!st.b||String(st.a.id)===String(st.b.id)){ $a('arenaCommentary').textContent='Нужно выбрать двух разных викингов.';return;}reset();st.running=true;$a('arenaCommentary').textContent='🔥 ВИКИНГИ ВЫХОДЯТ НА АРЕНУ!';write('⚔️ Бой начинается!');setTimeout(roundStep,750);}
  $a('arenaToggle')?.addEventListener('click',open);$a('arenaClose')?.addEventListener('click',close);$a('arenaStart')?.addEventListener('click',start);$a('arenaAgain')?.addEventListener('click',start);$a('arenaFighterA')?.addEventListener('change',sync);$a('arenaFighterB')?.addEventListener('change',sync);$a('arenaSwap')?.addEventListener('click',()=>{const x=$a('arenaFighterA').value;$a('arenaFighterA').value=$a('arenaFighterB').value;$a('arenaFighterB').value=x;sync();});
  document.querySelectorAll('[data-arena-action]').forEach(btn=>btn.addEventListener('click',()=>{if(!st.running){$a('arenaCommentary').textContent='Сначала нажмите «Начать бой».';return;}const side=st.round%2?'A':'B';st.queued[side]=btn.dataset.arenaAction;$a('arenaCommentary').textContent=`${side==='A'?st.a.nickname:st.b.nickname}: ${actionName(btn.dataset.arenaAction)}`;}));
})();
