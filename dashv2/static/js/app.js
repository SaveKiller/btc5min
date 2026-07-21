import { initChart, relayoutChart, resizeChart, setCandles, updateCurrentCandle } from "./chart.js";
import {
    applyButtonPreviews, layoutReplayScale, markStrategySelected, renderAccounts, renderAgentChat,
    renderAgentContext, renderAgentProposed, renderBotPanel, renderEnginePlugin, renderHistory,
    renderOrders, renderOutcome, renderRoundPickerDays, renderRoundPickerHours, renderRoundPickerRounds,
    renderSessionHistory, renderStakeButtons, renderTick, setDisconnectBanner, toggleHistorySession,
    updateTimelineSecLabel,
    renderStatsMode, renderStatsDays, renderStatsDayCalendar, renderStatsStrategySelect, renderStatsStrategyVersionSelect,
    renderStatsSimPeriodSelect, renderStatsSimulationSelect, renderStatsAnalyzeSimSelect, renderStatsJobUi,
    renderStatsBacktest, renderStatsAnalyze, renderStatsChat, statsSimMonthList,
} from "./render.js";

const REPLAY_SPEED_KEY = "dashv2_replay_speed";
const REPLAY_SPEEDS = [1, 2, 5];
const REPLAY_START_SEC_KEY = "dashv2_replay_start_sec";
const REPLAY_START_SEC_MIN = 5;
const REPLAY_START_SEC_MAX = 300;
const LEFT_TAB_KEY = "dashv2_left_tab";
const LEFT_TAB_IDS = [
    "candles-tab", "accounts-tab", "bot-tab",
    "agent-backtest-tab", "agent-analyze-tab", "agent-session-chat-tab",
];
const DEFAULT_LEFT_TAB = "accounts-tab";
const AGENT_HISTORY_POLL_MS = 5000;

const state = {
    session: null, tick: null, orders: null, historyRows: [],
    accounts: [], activeAccountId: null, activeAccount: null,
    strategies: [], activeStrategyIds: [], activeStrategies: [], selectedStrategyId: null,
    strategyCatalogVersions: {},
    strategyType: "deterministic", botAttachAllowed: true, botActive: false,
    chartPrevious: [], chartCurrent: null, scrubbing: false, wasPlaying: false,
    activeRoundTs: null, syncSizesOnNextOrders: false, loadedRoundDays: {},
    roundDays: [], roundNav: [], replaySpeed: loadStoredReplaySpeed(),
    startSec: loadStoredStartSec(),
    agentMessages: [], agentBusy: false, agentThinkingDetail: "", agentProposed: null,
    agentSessionId: null, executionSessions: [], agentFocus: null,
    sessionPickerDay: null,
    statsMode: "backtest",
    statsDayFrom: "", statsDayTo: "",
    statsStrategyId: null, statsStrategyVersion: null, statsAnalyzeId: null,
    statsAnalyzes: [],
    statsSimulations: [], statsSimulationId: null,
    statsSimMonthYm: null, statsSimSearch: "",
    statsAnalyzeSimulationIds: [],
    statsJobRunning: false, statsProgress: null,
    statsTable: null, statsSummary: null, statsRounds: null,
    statsDrill: { level: "hours", hour: null, slot: null },
    statsChatMessages: [], statsChatBusy: false,
};

const socket = io({ transports: ["websocket", "polling"] });
let accountModal = null;
let strategyModal = null;
let noticeModal = null;
let agentHistoryPollTimer = null;


function emitAck(event, payload = {}) {
    return new Promise((resolve, reject) => {
        socket.emit(event, payload, (res) => {
            if (!res) return reject(new Error(`no ack for ${event}`));
            if (res.error) return reject(new Error(res.error));
            resolve(res);
        });
    });
}


function showNotice(title, body) {
    document.getElementById("noticeModalTitle").textContent = title;
    document.getElementById("noticeModalBody").textContent = body;
    noticeModal.show();
}


function handleUiError(err) {
    const msg = err?.message || String(err);
    if (msg === "no round loaded") {
        showNotice("Round non caricato", "Carica prima un round dal picker, poi potrai avviare il replay.");
        return;
    }
    alert(msg);
}


function applyActiveStrategies(payload) {
    if (payload.active_strategies) {
        state.activeStrategies = payload.active_strategies;
        state.activeStrategyIds = payload.active_strategies.map((e) => e.id);
        return;
    }
    if (payload.active_strategy_ids) {
        state.activeStrategyIds = payload.active_strategy_ids;
        state.activeStrategies = payload.active_strategy_ids.map((id) => {
            const prev = state.activeStrategies.find((e) => e.id === id);
            const tip = state.strategies.find((s) => s.id === id)?.version || 1;
            return { id, version: prev?.version ?? tip };
        });
    }
}


function loadStoredReplaySpeed() {
    const speed = Number(localStorage.getItem(REPLAY_SPEED_KEY));
    return REPLAY_SPEEDS.includes(speed) ? speed : 1;
}


function clampStartSec(sec) {
    const n = Math.round(Number(sec));
    if (!Number.isFinite(n)) return REPLAY_START_SEC_MAX;
    if (n < REPLAY_START_SEC_MIN) return REPLAY_START_SEC_MIN;
    if (n > REPLAY_START_SEC_MAX) return REPLAY_START_SEC_MAX;
    return n;
}


function loadStoredStartSec() {
    const raw = localStorage.getItem(REPLAY_START_SEC_KEY);
    if (raw == null) return REPLAY_START_SEC_MAX;
    return clampStartSec(raw);
}


function persistStartSec(sec) {
    const clamped = clampStartSec(sec);
    state.startSec = clamped;
    localStorage.setItem(REPLAY_START_SEC_KEY, String(clamped));
    document.getElementById("replayStartSec").value = String(clamped);
}


function syncStartSecForRound() {
    const clamped = clampStartSec(state.startSec);
    if (clamped !== state.startSec) persistStartSec(clamped);
    return clamped;
}


function loadStoredLeftTab() {
    const tabId = localStorage.getItem(LEFT_TAB_KEY);
    if (tabId === "stats-tab" || tabId === "agent-tab") return "agent-backtest-tab";
    return LEFT_TAB_IDS.includes(tabId) ? tabId : DEFAULT_LEFT_TAB;
}


function persistLeftTab(tabId) {
    if (!LEFT_TAB_IDS.includes(tabId)) return;
    localStorage.setItem(LEFT_TAB_KEY, tabId);
}


function initToolbarTooltips() {
    document.querySelectorAll(".toolbar [data-bs-toggle='tooltip']").forEach((el) => {
        bootstrap.Tooltip.getOrCreateInstance(el, {
            container: "body",
            delay: { show: 350, hide: 80 },
        });
    });
}


function refreshHistoryViews() {
    renderHistory(state.historyRows, { agentSessionId: state.agentSessionId });
    renderSessionHistory(state.historyRows, state.session?.session_id, state.agentSessionId);
    renderAgentContext(state);
}


function renderReplaySpeedButtons(speed) {
    document.querySelectorAll(".replay-speed-btn").forEach((btn) => {
        const active = Number(btn.dataset.speed) === speed;
        btn.classList.toggle("btn-primary", active);
        btn.classList.toggle("btn-outline-secondary", !active);
        btn.classList.toggle("active", active);
    });
}


function renderPlaybackButtons(playing) {
    const playBtn = document.getElementById("playBtn");
    const pauseBtn = document.getElementById("pauseBtn");
    playBtn.classList.toggle("btn-primary", playing);
    playBtn.classList.toggle("btn-outline-secondary", !playing);
    pauseBtn.classList.toggle("btn-primary", !playing);
    pauseBtn.classList.toggle("btn-outline-secondary", playing);
}


function applyReplaySpeed(speed, { persist = true, notify = true } = {}) {
    if (!REPLAY_SPEEDS.includes(speed)) return;
    state.replaySpeed = speed;
    renderReplaySpeedButtons(speed);
    if (persist) localStorage.setItem(REPLAY_SPEED_KEY, String(speed));
    if (notify) return emitAck("replay.speed", { speed });
    return Promise.resolve();
}


socket.on("connect", () => {
    setDisconnectBanner(false);
    renderReplaySpeedButtons(state.replaySpeed);
    emitAck("session.sync")
        .then(() => applyReplaySpeed(state.replaySpeed, { persist: false }))
        .catch(console.error);
    // Riallinea chat/busy dal server (risposta può essere su disco anche se l'evento era perso).
    if (state.activeAccountId) {
        loadAgentHistory();
    }
    loadAgentExecutions();
    loadStatsChatHistory();
    loadStatsAnalyzes();
});

socket.on("disconnect", () => setDisconnectBanner(true));
socket.on("connect_error", () => setDisconnectBanner(true));

function loadRound(market_start_ts) {
    socket.emit("round.load", { market_start_ts, start_sec: syncStartSecForRound() });
}

function updateRoundNavButtons() {
    const cur = state.activeRoundTs ?? state.session?.market_start_ts;
    const nav = state.roundNav;
    const idx = cur == null ? -1 : nav.indexOf(cur);
    document.getElementById("prevRoundBtn").disabled = idx <= 0;
    document.getElementById("nextRoundBtn").disabled = idx < 0 || idx >= nav.length - 1;
}

function loadAdjacentRound(direction) {
    const cur = state.activeRoundTs ?? state.session?.market_start_ts;
    if (cur == null) return;
    const idx = state.roundNav.indexOf(cur);
    if (idx < 0) return;
    const ts = state.roundNav[idx + direction];
    if (ts == null) return;
    loadRound(ts);
}

function applyOrderSizes(payload) {
    document.getElementById("sizeUpInput").value = String(payload.size_up_usd);
    document.getElementById("sizeDownInput").value = String(payload.size_down_usd);
}

function requestPreviews() {
    if (!state.session?.loaded || state.session.round_ended || state.scrubbing) return;
    if (state.tick?.preview) return;
    const size_up_usd = Number(document.getElementById("sizeUpInput").value) || 0;
    const size_down_usd = Number(document.getElementById("sizeDownInput").value) || 0;
    emitAck("order.preview", { size_up_usd, size_down_usd }).then((res) => {
        if (state.scrubbing || state.tick?.preview) return;
        applyButtonPreviews(state.tick, res.previews);
    }).catch(() => {});
}

function roundHourUtc(market_start_ts) {
    const h = new Date(market_start_ts * 1000).getUTCHours();
    return `${String(h).padStart(2, "0")}:00`;
}

function groupRoundsByHour(rounds) {
    const byHour = {};
    for (let h = 0; h < 24; h++) {
        const hour = `${String(h).padStart(2, "0")}:00`;
        byHour[hour] = [];
    }
    rounds.forEach((r) => {
        const hour = roundHourUtc(r.market_start_ts);
        byHour[hour].push(r);
    });
    return Object.keys(byHour).sort().map((hour_utc) => {
        const list = byHour[hour_utc].sort((a, b) => a.market_start_ts - b.market_start_ts);
        const present = list.filter((r) => r.present !== false).length;
        return {
            hour_utc,
            count: present,
            valid: present > 0,
            rounds: list,
        };
    });
}

function showRoundDays() {
    renderRoundPickerDays(state.roundDays, openRoundDay);
}

function showRoundHours(dayUtc, rounds) {
    renderRoundPickerHours(dayUtc, groupRoundsByHour(rounds), showRoundDays, (hourUtc) => {
        openRoundHour(dayUtc, hourUtc, rounds);
    });
}

function openRoundHour(dayUtc, hourUtc, rounds) {
    const filtered = rounds
        .filter((r) => roundHourUtc(r.market_start_ts) === hourUtc)
        .sort((a, b) => a.market_start_ts - b.market_start_ts);
    renderRoundPickerRounds(dayUtc, hourUtc, filtered, () => showRoundHours(dayUtc, rounds), loadRound);
}

function openRoundDay(dayUtc) {
    const cached = state.loadedRoundDays[dayUtc];
    if (cached) {
        showRoundHours(dayUtc, cached);
        return;
    }
    const menu = document.getElementById("roundPickerMenu");
    menu.innerHTML = `
        <li><button class="dropdown-item round-picker-back" type="button"><i class="bi bi-chevron-left me-1"></i>Giorni</button></li>
        <li><hr class="dropdown-divider"></li>
        <li><span class="dropdown-item-text text-muted-app tiny px-3">Caricamento…</span></li>`;
    menu.querySelector(".round-picker-back").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        showRoundDays();
    });
    emitAck("rounds.list", { day_utc: dayUtc }).then((res) => {
        state.loadedRoundDays[dayUtc] = res.rounds;
        showRoundHours(dayUtc, res.rounds);
    }).catch((e) => alert(e.message));
}

function applyAccountsPayload(payload) {
    const prevId = state.activeAccountId;
    state.accounts = payload.accounts || [];
    state.activeAccountId = payload.active_account_id ?? null;
    state.activeAccount = payload.active ?? null;
    renderAccounts(state);
    renderAgentContext(state);
    if (state.activeAccountId && state.activeAccountId !== prevId) {
        state.sessionPickerDay = null;
        // Lista sessioni + chat aggiornate via agent.session dal server.
        loadAgentExecutions();
    }
}

function setAgentStatus(text) {
    const el = document.getElementById("agentStatusLabel");
    if (!text) {
        el.classList.add("d-none");
        el.textContent = "";
        return;
    }
    el.classList.remove("d-none");
    el.textContent = text;
}

function applyAgentFocus(payload) {
    const prevSid = state.agentSessionId;
    state.agentSessionId = payload.agent_session_id ?? null;
    if (payload.sessions) state.executionSessions = payload.sessions;
    state.agentFocus = {
        market_start_ts: payload.market_start_ts ?? null,
        sec: payload.sec ?? null,
        is_live: !!payload.is_live,
        n_events: payload.n_events || 0,
        strategy_ids: payload.strategy_ids || [],
    };
    renderAgentContext(state);
    if (state.agentSessionId !== prevSid) {
        loadAgentHistory();
        renderHistory(state.historyRows, { agentSessionId: state.agentSessionId });
        renderSessionHistory(state.historyRows, state.session?.session_id, state.agentSessionId);
    }
}

function loadAgentExecutions() {
    return emitAck("agent.executions.list").then(applyAgentFocus).catch(() => {});
}

function finishAgentTurn() {
    stopAgentHistoryPoll();
    state.agentBusy = false;
    state.agentThinkingDetail = "";
    document.getElementById("agentSendBtn").disabled = false;
    setAgentStatus("");
    renderAgentChat(state.agentMessages);
}

function startAgentHistoryPoll() {
    if (agentHistoryPollTimer != null) return;
    agentHistoryPollTimer = setInterval(() => {
        if (!state.agentBusy) {
            stopAgentHistoryPoll();
            return;
        }
        loadAgentHistory();
    }, AGENT_HISTORY_POLL_MS);
}

function stopAgentHistoryPoll() {
    if (agentHistoryPollTimer == null) return;
    clearInterval(agentHistoryPollTimer);
    agentHistoryPollTimer = null;
}

function setAgentBusyUi(busy, detail) {
    state.agentBusy = busy;
    if (busy) {
        state.agentThinkingDetail = detail || state.agentThinkingDetail || "Thinking…";
    } else {
        state.agentThinkingDetail = "";
    }
    document.getElementById("agentSendBtn").disabled = busy;
    setAgentStatus(busy ? state.agentThinkingDetail : "");
    renderAgentChat(state.agentMessages, {
        thinking: busy,
        thinkingText: state.agentThinkingDetail,
    });
    if (busy) startAgentHistoryPoll();
    else stopAgentHistoryPoll();
}

function setAgentThinkingDetail(detail) {
    if (!state.agentBusy) return;
    state.agentThinkingDetail = detail || "Thinking…";
    setAgentStatus(state.agentThinkingDetail);
    const body = document.querySelector("#agentThinkingBubble .agent-thinking-text");
    if (body) {
        body.textContent = state.agentThinkingDetail;
        return;
    }
    renderAgentChat(state.agentMessages, {
        thinking: true,
        thinkingText: state.agentThinkingDetail,
    });
}

function loadAgentHistory() {
    if (!state.agentSessionId) {
        state.agentMessages = [];
        renderAgentChat([]);
        return Promise.resolve();
    }
    return emitAck("agent.chat.history", { session_id: state.agentSessionId }).then((res) => {
        state.agentMessages = res.messages || [];
        if (res.busy) {
            setAgentBusyUi(true, state.agentThinkingDetail || "Thinking…");
        } else if (state.agentBusy) {
            finishAgentTurn();
        } else {
            renderAgentChat(state.agentMessages);
        }
        return res;
    }).catch(() => {});
}

function sendAgentMessage() {
    if (state.agentBusy) return;
    const input = document.getElementById("agentChatInput");
    const text = input.value.trim();
    if (!text) return;
    if (!state.activeAccountId) return alert("Seleziona un account");
    if (!state.agentSessionId) return alert("Seleziona una sessione");
    input.value = "";
    state.agentMessages = [...state.agentMessages, { role: "user", content: text }];
    setAgentBusyUi(true);
    emitAck("agent.chat.send", {
        text,
        account_id: state.activeAccountId,
        selected_strategy_id: state.selectedStrategyId,
        session_id: state.agentSessionId,
        agent_session_id: state.agentSessionId,
    }).catch((err) => {
        alert(err);
        loadAgentHistory().finally(() => finishAgentTurn());
    });
}


function defaultStatsDayRange(roundDays) {
    const days = (roundDays || []).filter((d) => d.valid !== false).map((d) => d.day_utc);
    if (!days.length) return { from: "", to: "" };
    let from = days[0];
    let to = days[0];
    for (const d of days) {
        if (d < from) from = d;
        if (d > to) to = d;
    }
    return { from, to };
}


function ensureStatsDayDefaults() {
    if (state.statsDayFrom && state.statsDayTo) return;
    const { from, to } = defaultStatsDayRange(state.roundDays);
    state.statsDayFrom = from;
    state.statsDayTo = to;
    renderStatsDays(state.statsDayFrom, state.statsDayTo);
}


function readStatsDays() {
    return { day_from: state.statsDayFrom, day_to: state.statsDayTo };
}


function statsValidDays() {
    return new Set((state.roundDays || []).filter((d) => d.valid !== false).map((d) => d.day_utc));
}


function openStatsDayCalendar(role) {
    const menu = document.getElementById(role === "from" ? "statsDayFromMenu" : "statsDayToMenu");
    const selected = role === "from" ? state.statsDayFrom : state.statsDayTo;
    let ym = menu.dataset.viewYm;
    if (!ym) {
        if (selected) ym = selected.slice(0, 7);
        else {
            const days = [...statsValidDays()].sort();
            ym = days[0].slice(0, 7);
        }
    }
    renderStatsDayCalendar(menu, {
        role,
        selected,
        boundMin: role === "to" ? state.statsDayFrom : null,
        boundMax: role === "from" ? state.statsDayTo : null,
        validDays: statsValidDays(),
        viewYm: ym,
    });
}


function setStatsMode(mode) {
    state.statsMode = mode;
    renderStatsMode(mode);
}


function resetStatsDrill() {
    state.statsDrill = { level: "hours", hour: null, slot: null };
}


function setStatsBacktestResults({ table = null, summary = null, rounds = null } = {}) {
    state.statsTable = table;
    state.statsSummary = summary;
    state.statsRounds = rounds;
    resetStatsDrill();
    renderStatsBacktest(state);
}


function refreshStatsSimulationUi() {
    const months = statsSimMonthList(state.statsSimulations);
    if (!months.includes(state.statsSimMonthYm)) {
        state.statsSimMonthYm = months[0] || null;
    }
    state.statsSimMonthYm = renderStatsSimPeriodSelect(months, state.statsSimMonthYm);
    renderStatsSimulationSelect(
        state.statsSimulations, state.statsSimulationId, state.statsSimMonthYm, state.statsSimSearch);
}


function refreshStatsPanels() {
    renderStatsMode(state.statsMode);
    renderStatsDays(state.statsDayFrom, state.statsDayTo);
    renderStatsStrategySelect(state.strategies, state.statsStrategyId, state.statsStrategyVersion, state.statsJobRunning);
    refreshStatsSimulationUi();
    renderStatsAnalyzeSimSelect(state.statsSimulations, state.statsAnalyzeSimulationIds);
    renderStatsJobUi(state);
    renderStatsBacktest(state);
    renderStatsAnalyze(state);
}


function loadStatsAnalyzes() {
    return emitAck("stats.analyze.list").then((res) => {
        state.statsAnalyzes = res.analyzes || [];
        if (!state.statsAnalyzeId && state.statsAnalyzes.length) {
            state.statsAnalyzeId = state.statsAnalyzes[0].id;
        }
    }).catch(() => {});
}


function loadStatsSimulations() {
    return emitAck("stats.simulation.list").then((res) => {
        state.statsSimulations = res.simulations || [];
        if (state.statsSimulationId && !state.statsSimulations.some((s) => s.id === state.statsSimulationId)) {
            state.statsSimulationId = null;
        }
        refreshStatsSimulationUi();
        state.statsAnalyzeSimulationIds = state.statsAnalyzeSimulationIds.filter(
            (id) => state.statsSimulations.some((s) => s.id === id && s.has_orders));
        renderStatsAnalyzeSimSelect(state.statsSimulations, state.statsAnalyzeSimulationIds);
    }).catch(() => {});
}


function applyLoadedSimulation(sim) {
    state.statsSimulationId = sim.id;
    state.statsSimMonthYm = (sim.exec_at || sim.created_at_utc || "").slice(0, 7);
    state.statsStrategyId = sim.strategy_id;
    state.statsStrategyVersion = sim.strategy_version;
    state.statsDayFrom = sim.day_from;
    state.statsDayTo = sim.day_to;
    state.statsTable = sim.table || null;
    state.statsSummary = {
        ...(sim.summary || {}),
        created_at_utc: sim.created_at_utc || (sim.summary && sim.summary.created_at_utc),
    };
    state.statsRounds = sim.rounds || null;
    resetStatsDrill();
    renderStatsDays(state.statsDayFrom, state.statsDayTo);
    renderStatsStrategySelect(state.strategies, state.statsStrategyId, state.statsStrategyVersion, state.statsJobRunning);
    refreshStatsSimulationUi();
    renderStatsBacktest(state);
    renderStatsJobUi(state);
}


function loadStatsSimulation(simulationId) {
    if (!simulationId) return;
    return emitAck("stats.simulation.load", { simulation_id: simulationId }).then((res) => {
        applyLoadedSimulation(res.simulation);
    }).catch(handleUiError);
}


function loadStatsChatHistory() {
    return emitAck("stats.chat.history").then((res) => {
        state.statsChatMessages = res.messages || [];
        state.statsChatBusy = !!res.busy;
        renderStatsChat(state.statsChatMessages, { thinking: state.statsChatBusy });
        document.getElementById("statsSendBtn").disabled = state.statsChatBusy;
    }).catch(() => {});
}


function setStatsChatBusy(busy) {
    state.statsChatBusy = busy;
    document.getElementById("statsSendBtn").disabled = busy;
    const lab = document.getElementById("statsChatStatusLabel");
    lab.classList.toggle("d-none", !busy);
    lab.textContent = busy ? "Thinking…" : "";
    renderStatsChat(state.statsChatMessages, { thinking: busy });
}


function sendStatsMessage() {
    if (state.statsChatBusy) return;
    const simulation_ids = state.statsAnalyzeSimulationIds;
    if (!simulation_ids.length) return alert("Seleziona almeno una Simulation");
    const input = document.getElementById("statsChatInput");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    state.statsChatMessages = [...state.statsChatMessages, { role: "user", content: text }];
    setStatsChatBusy(true);
    emitAck("stats.chat.send", { text, simulation_ids }).catch((err) => {
        alert(err);
        loadStatsChatHistory().finally(() => setStatsChatBusy(false));
    });
}


function clearStatsChat() {
    if (state.statsChatBusy) return alert("Chat busy");
    emitAck("stats.chat.clear").then(() => {
        state.statsChatMessages = [];
        renderStatsChat([], { thinking: false });
    }).catch(handleUiError);
}


function startStatsBacktest() {
    const { day_from, day_to } = readStatsDays();
    const strategy_id = state.statsStrategyId;
    const s = state.strategies.find((x) => x.id === strategy_id);
    const strategy_version = state.statsStrategyVersion ?? s?.version ?? null;
    if (!strategy_id) return alert("Seleziona una strategy");
    if (!strategy_version) return alert("Seleziona una versione");
    if (!day_from || !day_to) return alert("Imposta il range giorni");
    state.statsStrategyId = strategy_id;
    state.statsStrategyVersion = strategy_version;
    state.statsJobRunning = true;
    state.statsProgress = null;
    setStatsBacktestResults({});
    renderStatsJobUi(state);
    emitAck("stats.backtest.start", { strategy_id, strategy_version, day_from, day_to }).catch((err) => {
        state.statsJobRunning = false;
        renderStatsJobUi(state);
        alert(err);
    });
}


function cancelStatsJob() {
    emitAck("stats.job.cancel").catch(handleUiError);
}


function applyStatsRules(rules) {
    if (!rules) return;
    const simulation_ids = state.statsAnalyzeSimulationIds;
    if (!simulation_ids.length) return alert("Seleziona almeno una Simulation");
    const payload = { rules, simulation_ids };
    if (state.statsAnalyzeId) payload.analyze_id = state.statsAnalyzeId;
    else payload.name = `auto-${Date.now().toString(36).slice(-6)}`;
    setStatsChatBusy(true);
    document.getElementById("statsChatStatusLabel").textContent = "Codegen + analisi in corso…";
    document.getElementById("statsChatStatusLabel").classList.remove("d-none");
    emitAck("stats.rules.apply", payload).catch((err) => {
        setStatsChatBusy(false);
        alert(err);
    });
}


function openAccountModal(mode, account = null) {
    document.getElementById("accountModalMode").value = mode;
    document.getElementById("accountModalId").value = account?.id || "";
    document.getElementById("accountModalName").value = account?.name || "";
    document.getElementById("accountModalBalance").value = account ? String(account.initial_balance_usd) : "10000";
    document.getElementById("accountModalNote").value = account?.note || "";
    const title = mode === "create" ? "New account" : (mode === "rename" ? "Rename account" : "Edit account");
    document.getElementById("accountModalTitle").textContent = title;
    document.getElementById("accountModalBalance").closest(".mb-3").style.display = mode === "rename" ? "none" : "";
    document.getElementById("accountModalNote").closest(".mb-0").style.display = mode === "rename" ? "none" : "";
    accountModal.show();
}

function saveAccountModal() {
    const mode = document.getElementById("accountModalMode").value;
    const name = document.getElementById("accountModalName").value.trim();
    const balance = Number(document.getElementById("accountModalBalance").value);
    const note = document.getElementById("accountModalNote").value;
    const accountId = document.getElementById("accountModalId").value;
    if (!name) return alert("Nome obbligatorio");
    let req;
    if (mode === "create") {
        req = emitAck("account.create", { name, initial_balance_usd: balance, note });
    } else if (mode === "rename") {
        req = emitAck("account.rename", { account_id: accountId, name });
    } else {
        req = emitAck("account.update", { account_id: accountId, name, initial_balance_usd: balance, note });
    }
    req.then(() => accountModal.hide()).catch(handleUiError);
}

function showStrategyModalTab(tabId) {
    const btn = document.getElementById(tabId);
    if (btn) bootstrap.Tab.getOrCreateInstance(btn).show();
}

function fillStrategyModalVersions(strategy, selectedVersion) {
    const sel = document.getElementById("strategyModalVersion");
    if (!strategy) {
        sel.innerHTML = `<option value="1">1</option>`;
        sel.value = "1";
        sel.disabled = true;
        return;
    }
    const versions = strategy.versions || [{ version: strategy.version || 1 }];
    sel.innerHTML = versions.map((v) =>
        `<option value="${v.version}">${v.version}</option>`).join("");
    const tip = strategy.version || 1;
    const pick = selectedVersion != null ? selectedVersion : tip;
    sel.value = String(pick);
    sel.disabled = false;
}

function applyStrategyVersionBase(strategy, version) {
    const versions = strategy.versions || [];
    const snap = versions.find((v) => v.version === version) || {
        rules: strategy.rules, coded_rules: strategy.coded_rules,
    };
    document.getElementById("strategyModalRules").value = snap.rules || "";
    document.getElementById("strategyModalRules").dataset.original = snap.rules || "";
    document.getElementById("strategyModalCodedRules").value = snap.coded_rules || "";
}

function catalogVersionFor(strategy) {
    const id = strategy.id;
    if (state.strategyCatalogVersions[id] != null) return state.strategyCatalogVersions[id];
    return strategy.version || 1;
}


function openStrategyModal(mode, strategy = null) {
    document.getElementById("strategyModalMode").value = mode;
    document.getElementById("strategyModalId").value = strategy?.id || "";
    document.getElementById("strategyModalName").value = strategy?.name || "";
    document.getElementById("strategyModalName").dataset.original = strategy?.name || "";
    document.getElementById("strategyModalDescription").value = strategy?.description || "";
    document.getElementById("strategyModalTitle").textContent = mode === "create" ? "New strategy" : "Edit strategy";
    const showRules = state.strategyType === "deterministic" || strategy?.type === "deterministic";
    document.getElementById("strategyModalRulesWrap").classList.toggle("d-none", !showRules);
    const openVer = strategy ? catalogVersionFor(strategy) : 1;
    fillStrategyModalVersions(strategy, openVer);
    if (strategy) applyStrategyVersionBase(strategy, openVer);
    else {
        document.getElementById("strategyModalRules").value = "";
        document.getElementById("strategyModalRules").dataset.original = "";
        document.getElementById("strategyModalCodedRules").value = "";
    }
    setStrategyModalBusy(false);
    clearStrategyGenerateLog();
    showStrategyModalTab("strategyRulesTab");
    strategyModal.show();
}

function clearStrategyGenerateLog() {
    const log = document.getElementById("strategyModalGenerateLog");
    log.value = "";
}

function appendStrategyGenerateLog(text) {
    if (!text) return;
    const log = document.getElementById("strategyModalGenerateLog");
    const line = text.trim();
    log.value = log.value ? `${log.value}\n${line}` : line;
    log.scrollTop = log.scrollHeight;
}

function setStrategyModalBusy(busy, text = "") {
    const prog = document.getElementById("strategyModalProgress");
    const saveBtn = document.getElementById("strategyModalSaveBtn");
    const cancelBtn = document.getElementById("strategyModalCancelBtn");
    const closeBtn = document.getElementById("strategyModalCloseBtn");
    prog.classList.toggle("d-none", !busy);
    prog.classList.toggle("d-flex", busy);
    if (text) {
        document.getElementById("strategyModalProgressText").textContent = busy ? "In corso…" : text;
        if (busy) appendStrategyGenerateLog(text);
    }
    saveBtn.disabled = busy;
    cancelBtn.disabled = busy;
    closeBtn.disabled = busy;
}

function refreshStrategyModalFromStrategy(s, name, description, rules) {
    document.getElementById("strategyModalMode").value = "edit";
    document.getElementById("strategyModalId").value = s.id;
    document.getElementById("strategyModalName").value = s.name || name;
    document.getElementById("strategyModalName").dataset.original = s.name || name;
    document.getElementById("strategyModalDescription").value = s.description ?? description;
    document.getElementById("strategyModalTitle").textContent = "Edit strategy";
    fillStrategyModalVersions(s, s.version);
    applyStrategyVersionBase(s, s.version);
}

function saveStrategyModal() {
    const mode = document.getElementById("strategyModalMode").value;
    const name = document.getElementById("strategyModalName").value.trim();
    const description = document.getElementById("strategyModalDescription").value;
    const rules = document.getElementById("strategyModalRules").value;
    const strategyId = document.getElementById("strategyModalId").value;
    const baseVersion = Number(document.getElementById("strategyModalVersion").value) || 1;
    if (!name) return alert("Name required");
    const isDet = state.strategyType === "deterministic" || (
        mode === "edit" && state.strategies.find((s) => s.id === strategyId)?.type === "deterministic"
    );
    if (isDet && !rules.trim()) return alert("Rules required for deterministic strategy");
    const original = document.getElementById("strategyModalRules").dataset.original || "";
    const rulesChanged = isDet && (mode === "create" || rules !== original);
    let req;
    if (mode === "create") {
        clearStrategyGenerateLog();
        setStrategyModalBusy(true, isDet ? "Generazione modulo Python…" : "Salvataggio…");
        req = emitAck("strategy.create", { name, type: state.strategyType, description, rules });
    } else {
        if (rulesChanged) clearStrategyGenerateLog();
        setStrategyModalBusy(true, rulesChanged ? "Rigenerazione modulo Python…" : "Salvataggio…");
        req = emitAck("strategy.update", {
            strategy_id: strategyId, name, description, rules,
            rules_changed: rulesChanged, base_version: baseVersion,
        });
    }
    req.then((res) => {
        const s = res.strategy;
        if (s) {
            state.selectedStrategyId = s.id;
            const idx = state.strategies.findIndex((x) => x.id === s.id);
            if (idx >= 0) state.strategies[idx] = { ...state.strategies[idx], ...s };
            else state.strategies = [s, ...state.strategies];
            // Versione catalogo = tip se regole rigenerate, altrimenti quella scelta nel modal.
            state.strategyCatalogVersions[s.id] = (isDet && rulesChanged) ? s.version : baseVersion;
        }
        setStrategyModalBusy(false);
        renderBotPanel(state);
        if (isDet && rulesChanged && s) {
            refreshStrategyModalFromStrategy(s, name, description, rules);
            showStrategyModalTab("strategyCodedRulesTab");
            return;
        }
        strategyModal.hide();
    }).catch((err) => {
        setStrategyModalBusy(false);
        alert(err);
    });
}

function selectLeftTab(tabId) {
    const el = document.getElementById(tabId);
    if (el) bootstrap.Tab.getOrCreateInstance(el).show();
}


socket.on("bootstrap", (payload) => {
    state.roundDays = payload.round_days || [];
    state.roundNav = payload.round_nav || [];
    state.accounts = payload.accounts || [];
    state.activeAccountId = payload.active_account_id ?? null;
    state.activeAccount = state.accounts.find((a) => a.id === state.activeAccountId) || null;
    state.strategies = payload.strategies || [];
    applyActiveStrategies(payload);
    state.botAttachAllowed = payload.bot_attach_allowed !== false;
    state.botActive = payload.bot_active === true;
    renderEnginePlugin(payload.engine_plugin);
    showRoundDays();
    updateRoundNavButtons();
    applyOrderSizes({ size_up_usd: payload.default_order_size_usd, size_down_usd: payload.default_order_size_usd });
    renderAccounts(state);
    renderAgentContext(state);
    loadAgentExecutions();
    ensureStatsDayDefaults();
    renderStatsStrategySelect(state.strategies, state.statsStrategyId, state.statsStrategyVersion, state.statsJobRunning);
    refreshStatsPanels();
});

socket.on("session", (payload) => {
    const prev = state.session;
    // Preview di scrub: non sovrascrivere progress/sec locali (altrimenti la label "salta" indietro).
    if (payload.preview && prev?.loaded) {
        state.session = { ...payload, progress: prev.progress, sec: prev.sec };
    } else {
        state.session = payload;
    }
    if (payload.engine_plugin !== undefined) renderEnginePlugin(payload.engine_plugin);
    if (payload.playing != null) renderPlaybackButtons(payload.playing);
    if (payload.replay_speed != null) applyReplaySpeed(payload.replay_speed, { persist: false, notify: false });
    if (payload.active_account_id !== undefined) state.activeAccountId = payload.active_account_id;
    if (payload.bot_attach_allowed !== undefined) state.botAttachAllowed = payload.bot_attach_allowed;
    if (payload.bot_active !== undefined) state.botActive = payload.bot_active === true;
    applyActiveStrategies(payload);
    if (!payload.round_ended) document.getElementById("orderOutcome").textContent = "---";
    if (payload.loaded && payload.market_start_ts !== state.activeRoundTs) {
        state.activeRoundTs = payload.market_start_ts;
        state.syncSizesOnNextOrders = true;
    }
    if (!payload.loaded) state.activeRoundTs = null;
    const roundStart = payload.loaded && payload.session_id && payload.session_id !== prev?.session_id;
    if (roundStart) selectLeftTab("candles-tab");
    updateRoundNavButtons();
    renderAccounts(state);
    renderTick(state);
    renderAgentContext(state);
});

socket.on("tick", (payload) => {
    state.tick = payload;
    renderTick(state);
    // I tick di scrub già includono previews al sec corretto; order.preview usererebbe self.sec reale.
    if (!payload.preview) requestPreviews();
});

socket.on("orders", (payload) => {
    state.orders = payload;
    if (state.syncSizesOnNextOrders) {
        applyOrderSizes(payload);
        state.syncSizesOnNextOrders = false;
        requestPreviews();
    }
    renderOrders(payload);
    renderAccounts(state);
});

socket.on("accounts", (payload) => applyAccountsPayload(payload));

socket.on("history", (payload) => {
    state.historyRows = payload.rows || [];
    if (payload.active_account_id !== undefined) state.activeAccountId = payload.active_account_id;
    if (payload.session_id !== undefined && state.session) {
        state.session = { ...state.session, session_id: payload.session_id };
    }
    refreshHistoryViews();
});

socket.on("chart", (payload) => {
    if (payload.full_reset) {
        state.chartPrevious = payload.previous || [];
        state.chartCurrent = payload.current;
        setCandles(state.chartPrevious, state.chartCurrent);
    } else if (payload.current) {
        state.chartCurrent = payload.current;
        updateCurrentCandle(payload.current);
    }
});

socket.on("round_end", (payload) => {
    renderOutcome(payload);
    state.session = { ...state.session, round_ended: true, tradable: false };
    renderTick(state);
});

socket.on("error", (payload) => handleUiError(new Error(payload.message || "error")));

socket.on("strategy.generate", (payload) => {
    const phase = payload.phase || "";
    const msg = payload.message || phase;
    if (phase === "error") {
        if (msg) appendStrategyGenerateLog(`ERRORE: ${msg}`);
        setStrategyModalBusy(false);
        return;
    }
    if (phase === "done") {
        if (msg) appendStrategyGenerateLog(msg);
        setStrategyModalBusy(false);
        return;
    }
    setStrategyModalBusy(true, msg);
});

socket.on("bot.status", (payload) => {
    if (payload.bot_attach_allowed !== undefined) state.botAttachAllowed = payload.bot_attach_allowed;
    if (payload.bot_active !== undefined) state.botActive = payload.bot_active === true;
    applyActiveStrategies(payload);
    if (payload.reason === "disconnected" || payload.reason?.startsWith?.("crashed")) {
        state.botActive = false;
    }
    renderBotPanel(state);
    renderAgentContext(state);
});

socket.on("strategies", (payload) => {
    if (payload.strategies) state.strategies = payload.strategies;
    applyActiveStrategies(payload);
    renderBotPanel(state);
    renderAgentContext(state);
    renderAgentProposed(state.agentProposed, state.selectedStrategyId);
    renderStatsStrategySelect(state.strategies, state.statsStrategyId, state.statsStrategyVersion, state.statsJobRunning);
    renderStatsJobUi(state);
});

socket.on("stats.job.progress", (payload) => {
    state.statsJobRunning = true;
    state.statsProgress = payload;
    renderStatsJobUi(state);
});

socket.on("stats.job.done", (payload) => {
    state.statsJobRunning = false;
    state.statsProgress = null;
    state.statsSummary = payload.summary || null;
    if (payload.kind === "backtest") {
        state.statsTable = payload.table || null;
        state.statsRounds = payload.rounds || null;
        if (payload.simulation_id) state.statsSimulationId = payload.simulation_id;
        resetStatsDrill();
        renderStatsBacktest(state);
    } else {
        state.statsSummary = payload.summary || null;
        setStatsChatBusy(false);
        renderStatsAnalyze(state);
    }
    renderStatsJobUi(state);
});

socket.on("stats.job.error", (payload) => {
    if (payload.kind === "chat" || payload.kind === "apply") {
        setStatsChatBusy(false);
    }
    if (payload.kind !== "chat") {
        state.statsJobRunning = false;
        state.statsProgress = null;
        renderStatsJobUi(state);
    }
    alert(payload.message || "stats error");
});

socket.on("stats.job.cancelled", () => {
    state.statsJobRunning = false;
    state.statsProgress = null;
    renderStatsJobUi(state);
});

socket.on("stats.chat.message", (payload) => {
    if (payload.message) {
        const last = state.statsChatMessages[state.statsChatMessages.length - 1];
        if (!last || last.ts !== payload.message.ts || last.content !== payload.message.content) {
            state.statsChatMessages = [...state.statsChatMessages, payload.message];
        }
        renderStatsChat(state.statsChatMessages, { thinking: state.statsChatBusy });
    }
    if (payload.proposed_rules?.rules) {
        applyStatsRules(payload.proposed_rules.rules);
        return;
    }
    setStatsChatBusy(false);
});

socket.on("stats.chat.status", (payload) => {
    if (payload.phase === "thinking") {
        setStatsChatBusy(true);
        return;
    }
    if (state.statsChatBusy) loadStatsChatHistory();
    else setStatsChatBusy(false);
});

socket.on("stats.analyzes", (payload) => {
    state.statsAnalyzes = payload.analyzes || [];
    if (payload.applied_id) {
        state.statsAnalyzeId = payload.applied_id;
        state.statsJobRunning = true;
        state.statsProgress = null;
    } else if (state.statsAnalyzeId && !state.statsAnalyzes.some((a) => a.id === state.statsAnalyzeId)) {
        state.statsAnalyzeId = state.statsAnalyzes[0]?.id || null;
    }
    renderStatsJobUi(state);
});

socket.on("stats.simulations", (payload) => {
    state.statsSimulations = payload.simulations || [];
    if (payload.selected_id) {
        state.statsSimulationId = payload.selected_id;
        const sim = state.statsSimulations.find((s) => s.id === payload.selected_id);
        if (sim) state.statsSimMonthYm = (sim.exec_at || sim.created_at_utc || "").slice(0, 7);
    } else if (state.statsSimulationId && !state.statsSimulations.some((s) => s.id === state.statsSimulationId)) {
        state.statsSimulationId = null;
    }
    state.statsAnalyzeSimulationIds = state.statsAnalyzeSimulationIds.filter(
        (id) => state.statsSimulations.some((s) => s.id === id && s.has_orders));
    refreshStatsSimulationUi();
    renderStatsAnalyzeSimSelect(state.statsSimulations, state.statsAnalyzeSimulationIds);
});

socket.on("agent.chat.message", (payload) => {
    if (payload.session_id && payload.session_id !== state.agentSessionId) return;
    if (payload.message) {
        const last = state.agentMessages[state.agentMessages.length - 1];
        if (!last || last.ts !== payload.message.ts || last.content !== payload.message.content) {
            state.agentMessages = [...state.agentMessages, payload.message];
        }
    }
    if (payload.proposed_rules !== undefined) {
        state.agentProposed = payload.proposed_rules;
        renderAgentProposed(state.agentProposed, state.selectedStrategyId);
    }
    finishAgentTurn();
});

socket.on("agent.session.deleted", (payload) => {
    applyAgentFocus(payload);
    state.agentMessages = [];
    state.agentProposed = null;
    renderAgentChat([]);
    renderAgentProposed(null, null);
});

socket.on("agent.chat.status", (payload) => {
    if (payload.phase === "thinking") {
        const detail = payload.detail || "Thinking…";
        if (state.agentBusy) setAgentThinkingDetail(detail);
        else setAgentBusyUi(true, detail);
        return;
    }
    // idle: riallinea da disco (evento message può essere andato perso).
    if (state.agentBusy) {
        loadAgentHistory();
        return;
    }
    setAgentStatus("");
});

socket.on("agent.chat.error", (payload) => {
    alert(payload.message || "agent error");
    loadAgentHistory().finally(() => finishAgentTurn());
});

socket.on("agent.session", (payload) => {
    applyAgentFocus(payload);
});


document.getElementById("playBtn").addEventListener("click", () => {
    emitAck("replay.play", { start_sec: syncStartSecForRound() }).catch(handleUiError);
});
document.getElementById("pauseBtn").addEventListener("click", () => emitAck("replay.pause").catch(handleUiError));
document.querySelectorAll(".replay-speed-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyReplaySpeed(Number(btn.dataset.speed)).catch(handleUiError));
});
document.getElementById("replayStartSec").addEventListener("change", () => {
    persistStartSec(document.getElementById("replayStartSec").value);
});
document.getElementById("prevRoundBtn").addEventListener("click", () => loadAdjacentRound(-1));
document.getElementById("nextRoundBtn").addEventListener("click", () => loadAdjacentRound(1));

const slider = document.getElementById("timelineSlider");
let scrubPreviewRaf = 0;

function scrubPreview(sec) {
    if (scrubPreviewRaf) cancelAnimationFrame(scrubPreviewRaf);
    scrubPreviewRaf = requestAnimationFrame(() => {
        scrubPreviewRaf = 0;
        emitAck("replay.preview", { sec }).catch(() => {});
    });
}

slider.addEventListener("pointerdown", () => {
    state.scrubbing = true;
    state.wasPlaying = !!state.session?.playing;
    emitAck("replay.pause").catch(() => {});
});
slider.addEventListener("input", () => {
    const progress = Number(slider.value);
    const sec = 300 - progress;
    if (state.session) state.session = { ...state.session, progress, sec };
    // Solo la label segue il drag; il resto UI arriva dal preview async.
    updateTimelineSecLabel(sec, progress);
    scrubPreview(sec);
});
slider.addEventListener("pointerup", () => {
    if (scrubPreviewRaf) {
        cancelAnimationFrame(scrubPreviewRaf);
        scrubPreviewRaf = 0;
    }
    state.scrubbing = false;
    const sec = 300 - Number(slider.value);
    emitAck("replay.seek", { sec, resume: state.wasPlaying }).catch(handleUiError);
});

function bindSize(side, inputId) {
    const input = document.getElementById(inputId);
    const push = () => {
        const size = Number(input.value);
        if (size > 0) emitAck("order.size", { side, size_usd: size }).catch(handleUiError);
        requestPreviews();
    };
    input.addEventListener("input", requestPreviews);
    input.addEventListener("change", push);
    document.querySelector(`.stake[data-side="${side}"]`)?.addEventListener("click", (e) => {
        const btn = e.target.closest(".stake-btn");
        if (!btn) return;
        input.value = btn.dataset.amount;
        push();
    });
}
bindSize("Up", "sizeUpInput");
bindSize("Down", "sizeDownInput");

document.getElementById("buyUpBtn").addEventListener("click", () => {
    emitAck("order.place", { side: "Up", size_usd: Number(document.getElementById("sizeUpInput").value) }).catch(handleUiError);
});
document.getElementById("buyDownBtn").addEventListener("click", () => {
    emitAck("order.place", { side: "Down", size_usd: Number(document.getElementById("sizeDownInput").value) }).catch(handleUiError);
});

document.getElementById("exportCsvBtn").addEventListener("click", () => {
    const rows = state.historyRows;
    const header = ["Date","Time","Who","Direction","Outcome","Size","Entry","Exit","Final","PnL","SessionId"];
    const lines = [header.join(",")];
    rows.forEach((r) => {
        const entryQ = r.entry_quote_c != null ? `${r.entry_quote_c}c` : "—";
        const exitQ = r.exit_quote_c != null ? `${r.exit_quote_c}c` : "—";
        const entry = `${entryQ} / ${r.entry_sec}s`;
        const exit = r.exit_sec != null ? `${exitQ} / ${r.exit_sec}s` : "";
        lines.push([
            r.date_utc, r.time_utc, r.source || "user", r.direction, r.outcome ?? "", r.size_usd, entry, exit,
            r.final_pnl_usd ?? "", r.pnl_usd ?? "", r.session_id ?? "",
        ].join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "dashv2-history.csv";
    a.click();
});

document.getElementById("historyTableBody").addEventListener("click", (e) => {
    const row = e.target.closest(".history-session-row");
    if (!row) return;
    toggleHistorySession(row.dataset.sessionId);
    refreshHistoryViews();
});

document.getElementById("accountSelect").addEventListener("change", (e) => {
    const accountId = e.target.value || null;
    emitAck("account.select", { account_id: accountId }).catch(handleUiError);
});

document.getElementById("botActiveSwitch").addEventListener("change", (e) => {
    const active = e.target.checked;
    emitAck("bot.set_active", { active }).then((res) => {
        state.botActive = res.bot_active === true;
        renderBotPanel(state);
    }).catch((err) => {
        e.target.checked = state.botActive;
        alert(err);
    });
});

document.getElementById("strategyTypeSelect").addEventListener("change", (e) => {
    state.strategyType = e.target.value;
    state.selectedStrategyId = null;
    renderBotPanel(state);
});

document.getElementById("strategyNewBtn").addEventListener("click", () => openStrategyModal("create"));

document.getElementById("strategyEditBtn").addEventListener("click", () => {
    const id = state.selectedStrategyId;
    if (!id) return;
    const cur = state.strategies.find((s) => s.id === id);
    if (!cur) return;
    openStrategyModal("edit", cur);
});

document.getElementById("strategyCloneBtn").addEventListener("click", () => {
    const id = state.selectedStrategyId;
    if (!id) return;
    emitAck("strategy.clone", { strategy_id: id }).then((res) => {
        const s = res.strategy;
        state.selectedStrategyId = s.id;
        if (!state.strategies.some((x) => x.id === s.id)) {
            state.strategies = [s, ...state.strategies];
        }
        renderBotPanel(state);
        openStrategyModal("edit", s);
    }).catch(handleUiError);
});

document.getElementById("strategyDeleteBtn").addEventListener("click", () => {
    const id = state.selectedStrategyId;
    if (!id) return;
    emitAck("strategy.delete", { strategy_id: id }).then(() => {
        state.selectedStrategyId = null;
        renderBotPanel(state);
    }).catch(handleUiError);
});

document.getElementById("strategyModalSaveBtn").addEventListener("click", saveStrategyModal);

document.getElementById("strategyCatalogList").addEventListener("click", (e) => {
    const actionBtn = e.target.closest("[data-action]");
    if (actionBtn) {
        e.stopPropagation();
        const id = actionBtn.dataset.id;
        markStrategySelected(state, id);
        renderAgentContext(state);
        renderAgentProposed(state.agentProposed, state.selectedStrategyId);
        if (actionBtn.dataset.action === "load") {
            const s = state.strategies.find((x) => x.id === id);
            const ver = catalogVersionFor(s || { id, version: 1 });
            activateStrategy(id, ver);
        }
        return;
    }
    const item = e.target.closest(".strategy-catalog-item");
    if (!item) return;
    markStrategySelected(state, item.dataset.id);
    renderAgentContext(state);
    renderAgentProposed(state.agentProposed, state.selectedStrategyId);
});

document.getElementById("strategyCatalogList").addEventListener("dblclick", (e) => {
    if (e.target.closest("[data-action]")) return;
    const item = e.target.closest(".strategy-catalog-item");
    if (!item) return;
    const id = item.dataset.id;
    markStrategySelected(state, id);
    const cur = state.strategies.find((s) => s.id === id);
    if (!cur) return;
    openStrategyModal("edit", cur);
});

document.getElementById("botActiveList").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-unload]");
    if (!btn) return;
    deactivateStrategy(btn.dataset.unload);
});

function activateStrategy(id, version) {
    if (state.activeStrategyIds.includes(id)) return;
    emitAck("strategy.load", { strategy_id: id, strategy_version: version }).then((res) => {
        applyActiveStrategies(res);
        renderBotPanel(state);
    }).catch(handleUiError);
}

function deactivateStrategy(id) {
    if (!state.activeStrategyIds.includes(id)) return;
    emitAck("strategy.unload", { strategy_id: id }).then((res) => {
        applyActiveStrategies(res);
        renderBotPanel(state);
    }).catch(handleUiError);
}

document.getElementById("newAccountBtn").addEventListener("click", () => openAccountModal("create"));
document.getElementById("renameAccountBtn").addEventListener("click", () => {
    if (!state.activeAccount) return;
    openAccountModal("rename", state.activeAccount);
});
document.getElementById("editAccountBtn").addEventListener("click", () => {
    if (!state.activeAccount) return;
    openAccountModal("edit", state.activeAccount);
});
document.getElementById("unloadRoundBtn").addEventListener("click", () => {
    emitAck("round.unload", {}).catch(handleUiError);
});
document.getElementById("accountModalSaveBtn").addEventListener("click", saveAccountModal);

document.getElementById("agentSendBtn").addEventListener("click", sendAgentMessage);
document.getElementById("agentChatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendAgentMessage();
    }
});
document.getElementById("agentContextBody").addEventListener("click", (e) => {
    const unloadBtn = e.target.closest("[data-session-unload]");
    if (unloadBtn) {
        if (unloadBtn.disabled || unloadBtn.classList.contains("disabled")) return;
        emitAck("round.unload", {}).catch(handleUiError);
        return;
    }
    const dayBtn = e.target.closest("[data-session-day]");
    if (dayBtn) {
        e.preventDefault();
        e.stopPropagation();
        state.sessionPickerDay = dayBtn.dataset.sessionDay;
        renderAgentContext(state);
        const btn = document.getElementById("agentSessionSelectBtn");
        if (btn) bootstrap.Dropdown.getOrCreateInstance(btn).show();
        return;
    }
    const backBtn = e.target.closest("[data-session-back]");
    if (backBtn) {
        e.preventDefault();
        e.stopPropagation();
        state.sessionPickerDay = null;
        renderAgentContext(state);
        const btn = document.getElementById("agentSessionSelectBtn");
        if (btn) bootstrap.Dropdown.getOrCreateInstance(btn).show();
        return;
    }
    const sidBtn = e.target.closest("[data-session-id]");
    if (sidBtn) {
        emitAck("agent.session.select", { session_id: sidBtn.dataset.sessionId })
            .then(applyAgentFocus).catch(handleUiError);
    }
});
document.getElementById("agentContextBody").addEventListener("click", (e) => {
    const btn = e.target.closest("#agentDeleteSessionBtn");
    if (!btn || btn.disabled) return;
    if (!state.agentSessionId) return alert("Seleziona una sessione");
    const sid = state.agentSessionId;
    if (!confirm(`Delete session ${sid} permanently (chat, orders, exec log)?`)) return;
    emitAck("agent.session.delete", { session_id: sid }).then((res) => {
        applyAgentFocus(res);
        state.agentMessages = [];
        state.agentProposed = null;
        renderAgentChat([]);
        renderAgentProposed(null, null);
    }).catch(handleUiError);
});
document.getElementById("agentApplyRulesBtn").addEventListener("click", () => {
    const btn = document.getElementById("agentApplyRulesBtn");
    const sid = btn.dataset.strategyId;
    const rules = btn.dataset.rules;
    if (!sid || !rules) return;
    setAgentStatus("Applying rules (codegen)…");
    emitAck("agent.rules.apply", { strategy_id: sid, rules }).then(() => {
        setAgentStatus("");
        state.agentProposed = null;
        renderAgentProposed(null, null);
    }).catch((err) => {
        setAgentStatus("");
        alert(err);
    });
});

document.getElementById("leftTabs").addEventListener("shown.bs.tab", (e) => {
    persistLeftTab(e.target.id);
    if (e.target.id === "candles-tab") relayoutChart();
    if (e.target.id === "agent-session-chat-tab") {
        renderAgentContext(state);
        loadAgentExecutions();
    } else if (e.target.id === "agent-backtest-tab") {
        refreshAgentBacktestTab();
    } else if (e.target.id === "agent-analyze-tab") {
        refreshAgentAnalyzeTab();
    }
});

function refreshAgentBacktestTab() {
    setStatsMode("backtest");
    ensureStatsDayDefaults();
    refreshStatsPanels();
    loadStatsSimulations();
}

function refreshAgentAnalyzeTab() {
    setStatsMode("analyze");
    refreshStatsPanels();
    loadStatsAnalyzes();
    loadStatsSimulations();
    loadStatsChatHistory();
}
document.getElementById("statsDayFromBtn").addEventListener("show.bs.dropdown", () => {
    document.getElementById("statsDayFromMenu").dataset.viewYm = "";
    openStatsDayCalendar("from");
});
document.getElementById("statsDayToBtn").addEventListener("show.bs.dropdown", () => {
    document.getElementById("statsDayToMenu").dataset.viewYm = "";
    openStatsDayCalendar("to");
});
function onStatsDayMenuClick(role, e) {
    const nav = e.target.closest("[data-cal-nav]");
    if (nav) {
        const menu = document.getElementById(role === "from" ? "statsDayFromMenu" : "statsDayToMenu");
        const delta = Number(nav.dataset.calNav);
        const cur = menu.dataset.viewYm;
        const [y, m] = cur.split("-").map(Number);
        const d = new Date(Date.UTC(y, m - 1 + delta, 1));
        menu.dataset.viewYm = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
        openStatsDayCalendar(role);
        return;
    }
    const dayBtn = e.target.closest("button[data-day]");
    if (!dayBtn || dayBtn.disabled) return;
    const day = dayBtn.dataset.day;
    if (role === "from") {
        state.statsDayFrom = day;
        if (state.statsDayTo && state.statsDayTo < day) state.statsDayTo = day;
    } else {
        state.statsDayTo = day;
        if (state.statsDayFrom && state.statsDayFrom > day) state.statsDayFrom = day;
    }
    renderStatsDays(state.statsDayFrom, state.statsDayTo);
    bootstrap.Dropdown.getInstance(
        document.getElementById(role === "from" ? "statsDayFromBtn" : "statsDayToBtn"),
    ).hide();
}
document.getElementById("statsDayFromMenu").addEventListener("click", (e) => onStatsDayMenuClick("from", e));
document.getElementById("statsDayToMenu").addEventListener("click", (e) => onStatsDayMenuClick("to", e));
document.getElementById("statsStrategyMenu").addEventListener("click", (e) => {
    const item = e.target.closest("[data-value]");
    if (!item) return;
    state.statsStrategyId = item.dataset.value || null;
    state.statsStrategyVersion = null;
    renderStatsStrategySelect(state.strategies, state.statsStrategyId, state.statsStrategyVersion, state.statsJobRunning);
    renderStatsJobUi(state);
});
document.getElementById("statsStrategyVersionMenu").addEventListener("click", (e) => {
    const item = e.target.closest("[data-value]");
    if (!item) return;
    state.statsStrategyVersion = item.dataset.value ? Number(item.dataset.value) : null;
    renderStatsStrategyVersionSelect(
        state.strategies, state.statsStrategyId, state.statsStrategyVersion, state.statsJobRunning);
});
document.getElementById("strategyModalVersion").addEventListener("change", (e) => {
    const sid = document.getElementById("strategyModalId").value;
    const strategy = state.strategies.find((s) => s.id === sid);
    if (!strategy) return;
    applyStrategyVersionBase(strategy, Number(e.target.value));
    showStrategyModalTab("strategyRulesTab");
});
document.getElementById("statsAnalyzeSimMenu").addEventListener("change", (e) => {
    const cb = e.target.closest("input[data-sim-id]");
    if (!cb) return;
    const id = cb.getAttribute("data-sim-id");
    const set = new Set(state.statsAnalyzeSimulationIds);
    if (cb.checked) set.add(id);
    else set.delete(id);
    state.statsAnalyzeSimulationIds = [...set];
    renderStatsAnalyzeSimSelect(state.statsSimulations, state.statsAnalyzeSimulationIds);
});
document.getElementById("statsBacktestRunBtn").addEventListener("click", startStatsBacktest);
document.getElementById("statsJobCancelBtn").addEventListener("click", cancelStatsJob);
document.getElementById("statsBacktestTableBody").addEventListener("click", (e) => {
    const roundTr = e.target.closest("tr[data-round-ts]");
    if (roundTr) {
        const ts = Number(roundTr.getAttribute("data-round-ts"));
        selectLeftTab("candles-tab");
        loadRound(ts);
        return;
    }
    const tr = e.target.closest("tr[data-drill-key]");
    if (!tr || !state.statsRounds?.length) return;
    const key = tr.getAttribute("data-drill-key");
    if (state.statsDrill.level === "hours") {
        state.statsDrill = { level: "slots", hour: Number(key), slot: null };
    } else if (state.statsDrill.level === "slots") {
        state.statsDrill = { level: "days", hour: state.statsDrill.hour, slot: Number(key) };
    } else {
        return;
    }
    renderStatsBacktest(state);
});
document.getElementById("statsResultsBreadcrumb").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-crumb]");
    if (!btn) return;
    const crumb = btn.getAttribute("data-crumb");
    if (crumb === "hours") {
        state.statsDrill = { level: "hours", hour: null, slot: null };
    } else if (crumb === "slots") {
        state.statsDrill = { level: "slots", hour: state.statsDrill.hour, slot: null };
    }
    renderStatsBacktest(state);
});
document.getElementById("statsSimPeriodMenu").addEventListener("click", (e) => {
    const item = e.target.closest("[data-value]");
    if (!item) return;
    state.statsSimMonthYm = item.dataset.value;
    refreshStatsSimulationUi();
});
document.getElementById("statsSimSearch").addEventListener("input", (e) => {
    state.statsSimSearch = e.target.value;
    refreshStatsSimulationUi();
});
document.getElementById("statsSimulationMenu").addEventListener("click", (e) => {
    const item = e.target.closest("[data-value]");
    if (!item) return;
    const id = item.dataset.value || null;
    state.statsSimulationId = id;
    refreshStatsSimulationUi();
    if (id) loadStatsSimulation(id);
});
document.getElementById("statsSimulationDeleteBtn").addEventListener("click", () => {
    const id = state.statsSimulationId;
    if (!id) return;
    emitAck("stats.simulation.delete", { simulation_id: id }).then(() => {
        if (state.statsSimulationId === id) {
            state.statsSimulationId = null;
            setStatsBacktestResults({});
        }
        loadStatsSimulations();
    }).catch(handleUiError);
});
document.getElementById("statsSendBtn").addEventListener("click", sendStatsMessage);
document.getElementById("statsChatClearBtn").addEventListener("click", clearStatsChat);
document.getElementById("statsChatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendStatsMessage();
    }
});

renderStakeButtons();
renderReplaySpeedButtons(state.replaySpeed);
persistStartSec(state.startSec);
initToolbarTooltips();
initChart(document.getElementById("chartContainer"));
layoutReplayScale();
window.addEventListener("resize", () => { layoutReplayScale(); relayoutChart(); });
noticeModal = new bootstrap.Modal(document.getElementById("noticeModal"));
accountModal = new bootstrap.Modal(document.getElementById("accountModal"));
strategyModal = new bootstrap.Modal(document.getElementById("strategyModal"), {
    backdrop: "static",
    keyboard: false,
});
renderOrders({ open: [] });
refreshStatsPanels();
selectLeftTab(loadStoredLeftTab());

document.getElementById("openOrdersList").addEventListener("click", (e) => {
    const cancelBtn = e.target.closest(".cancel-order-btn");
    if (cancelBtn) {
        emitAck("order.cancel", { order_id: cancelBtn.dataset.id }).catch(handleUiError);
        return;
    }
    const btn = e.target.closest(".close-order-btn");
    if (!btn || btn.disabled) return;
    emitAck("order.close", { order_id: btn.dataset.id }).catch(handleUiError);
});
