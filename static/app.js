const state = { page: 1, pages: 1, mode: "general", datesLoaded: false, playerDetail: null, finishedAt: undefined, luckBrotherhood: "", luckText: "", luckBrotherhoods: [] };
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
  if (Number.isNaN(date.getTime())) return "Нет прогноза";
  // Показываем именно время прогноза, полученное сервером.
  // Не сравниваем его с часами браузера: прогноз может быть на текущее
  // или уже начавшееся время, но он всё равно должен быть виден.
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const mo = String(date.getMonth() + 1).padStart(2, "0");
  return `${hh}:${mm} ${dd}.${mo}`;
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
    // Основной источник — БД. Резерв — parsed из диагностического ответа.
    // Это закрывает случай, когда парсер уже нашёл прогноз, а запись БД ещё
    // не успела попасть в JSON-ответ.
    const debugBox = $("attackDebug");
    if (debugBox && data.debug) {
      const d = data.debug;
      debugBox.textContent = d.error
        ? `Диагностика: ${d.error}`
        : `Монах: ${d.monk_url || "—"}\nФинальный URL: ${d.final_url || "—"}\nHTTP: ${d.http_status ?? "—"}, ответ: ${d.response_bytes ?? "—"} байт\nМаркер погоды: ${d.weather_marker ? "найден" : "не найден"}\nИсточник: ${d.source || "—"}\nРаспознано: ${d.parsed || "НЕТ"}\nФрагмент: ${d.snippet || "—"}`;
      debugBox.classList.remove("hidden");
    }
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
      const gain = Number(member.stat_gain || 0);
      const gainHtml = gain > 0 ? `<em class="org-player-gain">+${fmt(gain)}</em>` : `<em class="org-player-gain zero">—</em>`;
      return (
      `<div class="org-player">
        <b class="org-player-place">${memberPlace}</b>
        <a class="org-player-name game-profile-link" href="https://playwekings.mobi/hero/detail?player=${member.id}"><span>${escapeHtml(member.nickname)}</span></a>
        <small>ур. ${member.level ?? "—"} · ${fmt(member.stat_sum)} ${gainHtml}</small>
        <button class="show-stats" data-player-id="${member.id}" title="Показать статистику" aria-label="Показать статистику игрока">▥</button>
      </div>`
      );
    }).join("");
    const weeklyTop = group.weekly_top?.length ? `
      <div class="org-weekly-top">
        <div class="org-weekly-title"><span>🏆</span><div class="org-weekly-title-text"><strong>ТОП-3 игроков ${type === "clan" ? "клана" : "братства"} за неделю</strong><small>Кто больше всего добавил статов</small></div></div>
        <div class="org-weekly-list">${group.weekly_top.map((item, index) => `
          <div class="org-weekly-item"><b>${index + 1}</b><a class="org-weekly-player game-profile-link" href="https://playwekings.mobi/hero/detail?player=${item.player_id}">${escapeHtml(item.nickname)}</a><strong>+${fmt(item.gain)}</strong></div>`).join("")}
        </div>
      </div>` : `<div class="org-weekly-top empty"><div class="org-weekly-title"><span>🏆</span><div><strong>ТОП-3 ${type === "clan" ? "клана" : "братства"} за неделю</strong><small>Пока недостаточно данных</small></div></div></div>`;
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
        <div class="organization-contribution-head"><div class="organization-contribution-main"><span>📈 Вклад в ${type === "clan" ? "клан" : "братство"}</span><b>${signedValue(group.stat_delta)}</b></div><small>Изменение суммы статов за выбранный период</small></div>
        <div class="membership-changes">${joined}${left}</div>
        ${weeklyTop}
        <div class="organization-player-list">${members}</div>
      </td>
    </tr>`;
  }).join("") : '<tr><td colspan="5" class="loading">Организации не найдены</td></tr>';
  hidePlayerDetail();
}


function renderLuckMembers(players) {
  const box = $("luckMemberBox");
  const list = $("luckMembers");
  box.classList.remove("hidden");
  list.innerHTML = players.length ? players.map(player => `
    <label class="luck-member-row">
      <input type="checkbox" class="luck-member-check" data-player-id="${player.id}">
      <span class="luck-member-name"><b>${escapeHtml(player.nickname)}</b><small>ур. ${player.level} · сила ${fmt(player.power)}</small></span>
      <select class="luck-member-amount" data-player-id="${player.id}" disabled aria-label="Количество удачи для ${escapeHtml(player.nickname)}">
        ${Array.from({length: 7}, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("")}
      </select>
    </label>`).join("") : '<p class="life-empty">В братстве нет участников.</p>';

  list.querySelectorAll(".luck-member-check").forEach(check => {
    check.onchange = () => {
      const amount = list.querySelector(`.luck-member-amount[data-player-id="${check.dataset.playerId}"]`);
      if (amount) amount.disabled = !check.checked;
      updateLuckCalculateState();
    };
  });
  updateLuckCalculateState();
}

function updateLuckCalculateState() {
  const selected = document.querySelectorAll(".luck-member-check:checked").length;
  $("luckCalculate").disabled = selected === 0;
}

async function loadLuckMembers(brotherhood) {
  state.luckBrotherhood = brotherhood;
  state.luckText = "";
  $("luckSubtitle").textContent = `Братство: ${brotherhood}`;
  $("luckActions").classList.add("hidden");
  $("luckMemberBox").classList.remove("hidden");
  $("luckMembers").innerHTML = '<p class="life-empty">Загрузка участников…</p>';
  $("luckResults").innerHTML = '<p class="life-empty">Выберите игроков и укажите, сколько удачи им нужно.</p>';
  const response = await fetch(`/api/luck/members?brotherhood=${encodeURIComponent(brotherhood)}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Не удалось загрузить участников");
  renderLuckMembers(data.players || []);
}

async function calculateLuck() {
  const checks = [...document.querySelectorAll(".luck-member-check:checked")];
  if (!state.luckBrotherhood || !checks.length) return;
  $("luckResults").innerHTML = '<p class="life-empty">Рассчитываем распределение…</p>';
  $("luckActions").classList.add("hidden");
  const requests = checks.map(check => {
    const amount = document.querySelector(`.luck-member-amount[data-player-id="${check.dataset.playerId}"]`);
    return { id: Number(check.dataset.playerId), amount: Number(amount?.value || 1) };
  });
  const response = await fetch("/api/luck", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({brotherhood: state.luckBrotherhood, requests})
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Не удалось рассчитать удачу");

  const lines = [];
  data.results.forEach(item => {
    const givers = item.givers.map(giver => `⚔️ ${giver.nickname}`).join(", ");
    const line = `🏆 ${item.receiver} получает ${item.received} из ${item.requested} удачи от ${givers}.`;
    lines.push(item.received < item.requested ? `${line} ⚠ Не хватило ${item.requested - item.received} удач.` : line);
  });
  state.luckText = [
    "Братство: Раздача удачи",
    "",
    ...lines
  ].join("\n");
  $("luckSummary").textContent = `Распределено ${data.total} / ${data.requested}` + (data.total < data.requested ? " · не хватает удачи" : "");
  $("luckActions").classList.remove("hidden");
  $("luckResults").innerHTML = data.results.length ? data.results.map(item => `
    <article class="luck-receiver">
      <div class="luck-receiver-head"><strong>🏆 ${escapeHtml(item.receiver)} получает ${item.received} из ${item.requested} удачи</strong><span>ур. ${item.level} · сила ${fmt(item.power)}</span></div>
      <div class="luck-result-line">${item.givers.length ? `от ${item.givers.map(giver => `<span class="luck-inline-giver">⚔️ ${escapeHtml(giver.nickname)}</span>`).join(", ")}` : "Удачу некому дать"}.${item.received < item.requested ? ` <span class="luck-shortage">Не хватило ${item.requested - item.received} удач.</span>` : ""}</div>
    </article>`).join("") : '<p class="life-empty">Распределить удачу невозможно.</p>';
}

async function loadLuckBrotherhoods() {
  const input = $("luckBrotherhoodSearch");
  state.luckBrotherhoods = [];
  input.value = state.luckBrotherhood || "";
  input.placeholder = "Загрузка братств…";
  const response = await fetch('/api/luck/brotherhoods');
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Не удалось загрузить список братств");
  state.luckBrotherhoods = Array.isArray(data.brotherhoods) ? data.brotherhoods : [];
  input.placeholder = state.luckBrotherhoods.length ? "Начните вводить название братства…" : "Братства не найдены";
  if (state.luckBrotherhood && state.luckBrotherhoods.includes(state.luckBrotherhood)) {
    input.value = state.luckBrotherhood;
    await loadLuckMembers(state.luckBrotherhood);
  }
}

function normalizeLuckSearch(value) {
  return String(value || "").trim().toLocaleLowerCase().replaceAll("ё", "е");
}

function hideLuckSuggestions() {
  const box = $("luckBrotherhoodSuggestions");
  box.classList.add("hidden");
  box.innerHTML = "";
}

function showLuckSuggestions(value) {
  const box = $("luckBrotherhoodSuggestions");
  const q = normalizeLuckSearch(value);
  if (!q || !state.luckBrotherhoods.length) {
    hideLuckSuggestions();
    return;
  }
  const starts = [];
  const contains = [];
  for (const name of state.luckBrotherhoods) {
    const n = normalizeLuckSearch(name);
    if (n.startsWith(q)) starts.push(name);
    else if (n.includes(q)) contains.push(name);
  }
  const matches = [...starts, ...contains].slice(0, 10);
  box.innerHTML = "";
  if (!matches.length) {
    box.innerHTML = '<div class="luck-suggestion-empty">Братство не найдено</div>';
    box.classList.remove("hidden");
    return;
  }
  matches.forEach(name => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "luck-suggestion";
    button.textContent = name;
    button.dataset.name = name;
    button.onclick = () => selectLuckBrotherhood(name);
    box.appendChild(button);
  });
  box.classList.remove("hidden");
}

async function selectLuckBrotherhood(name) {
  const input = $("luckBrotherhoodSearch");
  input.value = name;
  hideLuckSuggestions();
  await loadLuckMembers(name);
}

function clearLuckSelection() {
  state.luckBrotherhood = "";
  state.luckText = "";
  $("luckBrotherhoodSearch").value = "";
  $("luckMemberBox").classList.add("hidden");
  $("luckActions").classList.add("hidden");
  $("luckResults").innerHTML = '<p class="life-empty">Введите название братства и выберите его из подсказки.</p>';
  hideLuckSuggestions();
}

async function openLuck() {
  $("luckPanel").classList.remove("hidden");
  $("luckToggle").classList.add("active");
  $("luckToggle").setAttribute("aria-expanded", "true");
  await loadLuckBrotherhoods();
  $("luckPanel").scrollIntoView({behavior:"smooth", block:"start"});
}

function closeLuck() {
  $("luckPanel").classList.add("hidden");
  $("luckToggle").classList.remove("active");
  $("luckToggle").setAttribute("aria-expanded", "false");
}

async function copyLuck() {
  if (!state.luckText) return;
  try {
    await navigator.clipboard.writeText(state.luckText);
  } catch (_) {
    const area = document.createElement("textarea");
    area.value = state.luckText;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  const button = $("luckCopy");
  const old = button.textContent;
  button.textContent = "Скопировано";
  setTimeout(() => button.textContent = old, 1500);
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

$("luckClose").onclick = closeLuck;
$("luckToggle").onclick = () => $("luckPanel").classList.contains("hidden") ? openLuck().catch(error => { $("luckResults").innerHTML = `<p class="life-empty">${escapeHtml(error.message || "Не удалось загрузить список братств")}</p>`; }) : closeLuck();
$("luckBrotherhoodSearch").addEventListener("input", event => {
  const value = event.target.value;
  if (!value.trim()) {
    clearLuckSelection();
    return;
  }
  showLuckSuggestions(value);
});
$("luckBrotherhoodSearch").addEventListener("focus", event => showLuckSuggestions(event.target.value));
$("luckBrotherhoodSearch").addEventListener("keydown", event => {
  if (event.key === "Escape") { hideLuckSuggestions(); return; }
  if (event.key === "Enter") {
    const q = normalizeLuckSearch(event.target.value);
    const exact = state.luckBrotherhoods.find(name => normalizeLuckSearch(name) === q);
    if (exact) { event.preventDefault(); selectLuckBrotherhood(exact).catch(error => { $("luckResults").innerHTML = `<p class="life-empty">${escapeHtml(error.message || "Не удалось загрузить участников")}</p>`; }); }
  }
});
document.addEventListener("click", event => {
  const wrap = document.querySelector(".luck-search-wrap");
  if (wrap && !wrap.contains(event.target)) hideLuckSuggestions();
});
$("luckSelectAll").onclick = () => {
  document.querySelectorAll(".luck-member-check").forEach(check => {
    check.checked = true;
    const amount = document.querySelector(`.luck-member-amount[data-player-id="${check.dataset.playerId}"]`);
    if (amount) amount.disabled = false;
  });
  updateLuckCalculateState();
};
$("luckClearAll").onclick = () => {
  document.querySelectorAll(".luck-member-check").forEach(check => {
    check.checked = false;
    const amount = document.querySelector(`.luck-member-amount[data-player-id="${check.dataset.playerId}"]`);
    if (amount) amount.disabled = true;
  });
  updateLuckCalculateState();
};
$("luckCalculate").onclick = () => calculateLuck().catch(error => {
  $("luckResults").innerHTML = `<p class="life-empty">${escapeHtml(error.message || "Ошибка расчёта")}</p>`;
});
$("luckCopy").onclick = copyLuck;

$("todayBadge").textContent = new Date().toLocaleDateString("ru-RU", {
  day: "2-digit", month: "short"
}).replace(".", "").toUpperCase();
syncMobileNav();
if ($("attackRefresh")) $("attackRefresh").onclick = refreshAttacks;
loadStatus().catch(() => {});
loadPlayers().catch(() => $("rows").innerHTML = '<tr><td colspan="7" class="loading">Не удалось загрузить данные</td></tr>');
setInterval(() => loadStatus().catch(() => {}), 30000);
