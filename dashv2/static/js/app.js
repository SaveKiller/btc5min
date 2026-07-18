import { initChart, relayoutChart, resizeChart, setCandles, updateCurrentCandle } from "./chart.js";
import {
    applyButtonPreviews, layoutReplayScale, renderAccounts, renderBotPanel, renderEnginePlugin, renderHistory,
    renderOrders, renderOutcome, renderRoundPickerDays, renderRoundPickerHours, renderRoundPickerRounds,
    renderStakeButtons, renderTick, setDisconnectBanner, toggleHistorySession,
} from "./render.js";

const REPLAY_SPEED_KEY = "dashv2_replay_speed";
const REPLAY_SPEEDS = [1, 2, 5];
const LEFT_TAB_KEY = "dashv2_left_tab";
const LEFT_TAB_IDS = ["candles-tab", "accounts-tab", "bot-tab"];
const DEFAULT_LEFT_TAB = "accounts-tab";

const state = {
    session: null, tick: null, orders: null, historyRows: [],
    accounts: [], activeAccountId: null, activeAccount: null,
    strategies: [], activeStrategyIds: [], selectedStrategyId: null,
    strategyType: "deterministic", botAttachAllowed: true, botActive: false,
    chartPrevious: [], chartCurrent: null, chartFreeView: false, scrubbing: false, wasPlaying: false,
    activeRoundTs: null, syncSizesOnNextOrders: false, loadedRoundDays: {},
    roundDays: [], roundNav: [], replaySpeed: loadStoredReplaySpeed(),
};

const socket = io({ transports: ["websocket", "polling"] });
let accountModal = null;
let strategyModal = null;


function emitAck(event, payload = {}) {
    return new Promise((resolve, reject) => {
        socket.emit(event, payload, (res) => {
            if (!res) return reject(new Error(`no ack for ${event}`));
            if (res.error) return reject(new Error(res.error));
            resolve(res);
        });
    });
}


function loadStoredReplaySpeed() {
    const speed = Number(localStorage.getItem(REPLAY_SPEED_KEY));
    return REPLAY_SPEEDS.includes(speed) ? speed : 1;
}


function loadStoredLeftTab() {
    const tabId = localStorage.getItem(LEFT_TAB_KEY);
    return LEFT_TAB_IDS.includes(tabId) ? tabId : DEFAULT_LEFT_TAB;
}


function persistLeftTab(tabId) {
    if (!LEFT_TAB_IDS.includes(tabId)) return;
    localStorage.setItem(LEFT_TAB_KEY, tabId);
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
});

socket.on("disconnect", () => setDisconnectBanner(true));
socket.on("connect_error", () => setDisconnectBanner(true));

function loadRound(market_start_ts) {
    socket.emit("round.load", { market_start_ts });
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
    state.accounts = payload.accounts || [];
    state.activeAccountId = payload.active_account_id ?? null;
    state.activeAccount = payload.active ?? null;
    renderAccounts(state);
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
    req.then(() => accountModal.hide()).catch(alert);
}

function openStrategyModal(mode, strategy = null) {
    document.getElementById("strategyModalMode").value = mode;
    document.getElementById("strategyModalId").value = strategy?.id || "";
    document.getElementById("strategyModalName").value = strategy?.name || "";
    document.getElementById("strategyModalDescription").value = strategy?.description || "";
    document.getElementById("strategyModalRules").value = strategy?.rules || "";
    document.getElementById("strategyModalRules").dataset.original = strategy?.rules || "";
    document.getElementById("strategyModalTitle").textContent = mode === "create" ? "New strategy" : "Edit strategy";
    const showRules = state.strategyType === "deterministic" || strategy?.type === "deterministic";
    document.getElementById("strategyModalRulesWrap").classList.toggle("d-none", !showRules);
    setStrategyModalBusy(false);
    strategyModal.show();
}

function setStrategyModalBusy(busy, text = "") {
    const prog = document.getElementById("strategyModalProgress");
    const saveBtn = document.getElementById("strategyModalSaveBtn");
    const cancelBtn = document.getElementById("strategyModalCancelBtn");
    prog.classList.toggle("d-none", !busy);
    if (text) document.getElementById("strategyModalProgressText").textContent = text;
    saveBtn.disabled = busy;
    cancelBtn.disabled = busy;
}

function saveStrategyModal() {
    const mode = document.getElementById("strategyModalMode").value;
    const name = document.getElementById("strategyModalName").value.trim();
    const description = document.getElementById("strategyModalDescription").value;
    const rules = document.getElementById("strategyModalRules").value;
    const strategyId = document.getElementById("strategyModalId").value;
    if (!name) return alert("Name required");
    const isDet = state.strategyType === "deterministic" || (
        mode === "edit" && state.strategies.find((s) => s.id === strategyId)?.type === "deterministic"
    );
    if (isDet && !rules.trim()) return alert("Rules required for deterministic strategy");
    let req;
    if (mode === "create") {
        setStrategyModalBusy(true, isDet ? "Generating Python module…" : "Saving…");
        req = emitAck("strategy.create", { name, type: state.strategyType, description, rules });
    } else {
        const original = document.getElementById("strategyModalRules").dataset.original || "";
        const rulesChanged = isDet && rules !== original;
        setStrategyModalBusy(true, rulesChanged ? "Regenerating Python module…" : "Saving…");
        req = emitAck("strategy.update", {
            strategy_id: strategyId, name, description, rules, rules_changed: rulesChanged,
        });
    }
    req.then((res) => {
        if (res.strategy) state.selectedStrategyId = res.strategy.id;
        setStrategyModalBusy(false);
        strategyModal.hide();
        renderBotPanel(state);
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
    state.activeStrategyIds = payload.active_strategy_ids || [];
    state.botAttachAllowed = payload.bot_attach_allowed !== false;
    state.botActive = payload.bot_active === true;
    renderEnginePlugin(payload.engine_plugin);
    showRoundDays();
    updateRoundNavButtons();
    applyOrderSizes({ size_up_usd: payload.default_order_size_usd, size_down_usd: payload.default_order_size_usd });
    renderAccounts(state);
});

socket.on("session", (payload) => {
    const prev = state.session;
    state.session = payload;
    if (payload.engine_plugin !== undefined) renderEnginePlugin(payload.engine_plugin);
    if (payload.playing != null) renderPlaybackButtons(payload.playing);
    if (payload.replay_speed != null) applyReplaySpeed(payload.replay_speed, { persist: false, notify: false });
    if (payload.active_account_id !== undefined) state.activeAccountId = payload.active_account_id;
    if (payload.bot_attach_allowed !== undefined) state.botAttachAllowed = payload.bot_attach_allowed;
    if (payload.bot_active !== undefined) state.botActive = payload.bot_active === true;
    if (payload.active_strategy_ids) state.activeStrategyIds = payload.active_strategy_ids;
    if (!payload.round_ended) document.getElementById("orderOutcome").textContent = "---";
    if (payload.loaded && payload.market_start_ts !== state.activeRoundTs) {
        state.activeRoundTs = payload.market_start_ts;
        state.syncSizesOnNextOrders = true;
    }
    const roundStart = payload.loaded && payload.sec === 300 && (
        !prev?.loaded || prev.market_start_ts !== payload.market_start_ts || prev.round_ended
    );
    if (roundStart) {
        state.chartFreeView = true;
        selectLeftTab("candles-tab");
    }
    updateRoundNavButtons();
    renderAccounts(state);
    renderTick(state);
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
    renderHistory(state.historyRows);
});

socket.on("chart", (payload) => {
    if (payload.full_reset) {
        state.chartPrevious = payload.previous || [];
        state.chartCurrent = payload.current;
        const freeView = state.chartFreeView;
        state.chartFreeView = false;
        setCandles(state.chartPrevious, state.chartCurrent, { freeView });
    } else if (payload.current) {
        state.chartCurrent = payload.current;
        updateCurrentCandle(payload.current);
    }
});

socket.on("round_end", (payload) => {
    renderOutcome(payload);
    state.session = { ...state.session, round_ended: true, tradable: false };
    renderTick(state);
    selectLeftTab("accounts-tab");
});

socket.on("action", (payload) => {
    if (payload.cmd === "order.close") selectLeftTab("accounts-tab");
});

socket.on("error", (payload) => alert(payload.message || "error"));

socket.on("strategy.generate", (payload) => {
    const phase = payload.phase || "";
    const msg = payload.message || phase;
    if (phase === "error") {
        setStrategyModalBusy(false);
        return;
    }
    if (phase === "done") {
        setStrategyModalBusy(false, msg);
        return;
    }
    setStrategyModalBusy(true, msg);
});

socket.on("bot.status", (payload) => {
    if (payload.bot_attach_allowed !== undefined) state.botAttachAllowed = payload.bot_attach_allowed;
    if (payload.bot_active !== undefined) state.botActive = payload.bot_active === true;
    if (payload.active_strategy_ids) state.activeStrategyIds = payload.active_strategy_ids;
    if (payload.reason === "disconnected" || payload.reason?.startsWith?.("crashed")) {
        state.botActive = false;
    }
    renderBotPanel(state);
});

socket.on("strategies", (payload) => {
    if (payload.strategies) state.strategies = payload.strategies;
    if (payload.active_strategy_ids) state.activeStrategyIds = payload.active_strategy_ids;
    renderBotPanel(state);
});


document.getElementById("playBtn").addEventListener("click", () => emitAck("replay.play").catch(alert));
document.getElementById("pauseBtn").addEventListener("click", () => emitAck("replay.pause").catch(alert));
document.querySelectorAll(".replay-speed-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyReplaySpeed(Number(btn.dataset.speed)).catch(alert));
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
    renderTick(state);
    scrubPreview(sec);
});
slider.addEventListener("pointerup", () => {
    if (scrubPreviewRaf) {
        cancelAnimationFrame(scrubPreviewRaf);
        scrubPreviewRaf = 0;
    }
    state.scrubbing = false;
    const sec = 300 - Number(slider.value);
    emitAck("replay.seek", { sec, resume: state.wasPlaying }).catch(alert);
});

function bindSize(side, inputId) {
    const input = document.getElementById(inputId);
    const push = () => {
        const size = Number(input.value);
        if (size > 0) emitAck("order.size", { side, size_usd: size }).catch(alert);
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
    emitAck("order.place", { side: "Up", size_usd: Number(document.getElementById("sizeUpInput").value) }).catch(alert);
});
document.getElementById("buyDownBtn").addEventListener("click", () => {
    emitAck("order.place", { side: "Down", size_usd: Number(document.getElementById("sizeDownInput").value) }).catch(alert);
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
    renderHistory(state.historyRows);
});

document.getElementById("accountSelect").addEventListener("change", (e) => {
    const accountId = e.target.value || null;
    emitAck("account.select", { account_id: accountId }).catch(alert);
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

document.getElementById("strategyDeleteBtn").addEventListener("click", () => {
    const id = state.selectedStrategyId;
    if (!id) return;
    emitAck("strategy.delete", { strategy_id: id }).then(() => {
        state.selectedStrategyId = null;
        renderBotPanel(state);
    }).catch(alert);
});

document.getElementById("strategyModalSaveBtn").addEventListener("click", saveStrategyModal);

document.getElementById("strategyCatalogList").addEventListener("click", (e) => {
    const actionBtn = e.target.closest("[data-action]");
    if (actionBtn) {
        e.stopPropagation();
        const id = actionBtn.dataset.id;
        state.selectedStrategyId = id;
        if (actionBtn.dataset.action === "load") activateStrategy(id);
        return;
    }
    const item = e.target.closest(".strategy-catalog-item");
    if (!item) return;
    state.selectedStrategyId = item.dataset.id;
    renderBotPanel(state);
});

document.getElementById("strategyCatalogList").addEventListener("dblclick", (e) => {
    if (e.target.closest("[data-action]")) return;
    const item = e.target.closest(".strategy-catalog-item");
    if (!item) return;
    const id = item.dataset.id;
    state.selectedStrategyId = id;
    if (state.activeStrategyIds.includes(id)) deactivateStrategy(id);
    else activateStrategy(id);
});

document.getElementById("botActiveList").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-unload]");
    if (!btn) return;
    deactivateStrategy(btn.dataset.unload);
});

function activateStrategy(id) {
    if (state.activeStrategyIds.includes(id)) return;
    emitAck("strategy.load", { strategy_id: id }).then((res) => {
        state.activeStrategyIds = res.active_strategy_ids || [];
        renderBotPanel(state);
    }).catch(alert);
}

function deactivateStrategy(id) {
    if (!state.activeStrategyIds.includes(id)) return;
    emitAck("strategy.unload", { strategy_id: id }).then((res) => {
        state.activeStrategyIds = res.active_strategy_ids || [];
        renderBotPanel(state);
    }).catch(alert);
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
document.getElementById("accountModalSaveBtn").addEventListener("click", saveAccountModal);

document.getElementById("leftTabs").addEventListener("shown.bs.tab", (e) => {
    persistLeftTab(e.target.id);
    if (e.target.id === "candles-tab") relayoutChart();
});

renderStakeButtons();
renderReplaySpeedButtons(state.replaySpeed);
initChart(document.getElementById("chartContainer"));
layoutReplayScale();
window.addEventListener("resize", () => { layoutReplayScale(); relayoutChart(); });
accountModal = new bootstrap.Modal(document.getElementById("accountModal"));
strategyModal = new bootstrap.Modal(document.getElementById("strategyModal"));
renderOrders({ open: [] });
selectLeftTab(loadStoredLeftTab());

document.getElementById("openOrdersList").addEventListener("click", (e) => {
    const cancelBtn = e.target.closest(".cancel-order-btn");
    if (cancelBtn) {
        emitAck("order.cancel", { order_id: cancelBtn.dataset.id }).catch(alert);
        return;
    }
    const btn = e.target.closest(".close-order-btn");
    if (!btn || btn.disabled) return;
    emitAck("order.close", { order_id: btn.dataset.id }).catch(alert);
});
