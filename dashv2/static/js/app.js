import { initChart, setCandles, updateCurrentCandle } from "./chart.js";
import {
    applyButtonPreviews, layoutReplayScale, renderHistory, renderOrders, renderOutcome,
    renderRoundPickerDays, renderRoundPickerRounds, renderStakeButtons, renderTick, setDisconnectBanner,
} from "./render.js";

const state = {
    session: null, tick: null, orders: null, historyRows: [],
    chartPrevious: [], chartCurrent: null, scrubbing: false, wasPlaying: false,
    activeRoundTs: null, syncSizesOnNextOrders: false, loadedRoundDays: {},
    roundDays: [],
};

const socket = io({ transports: ["websocket", "polling"] });


function emitAck(event, payload = {}) {
    return new Promise((resolve, reject) => {
        socket.emit(event, payload, (res) => {
            if (!res) return reject(new Error(`no ack for ${event}`));
            if (res.error) return reject(new Error(res.error));
            resolve(res);
        });
    });
}


socket.on("connect", () => {
    setDisconnectBanner(false);
    emitAck("session.sync").catch(console.error);
});

socket.on("disconnect", () => setDisconnectBanner(true));

socket.on("connect_error", () => setDisconnectBanner(true));

function loadRound(market_start_ts) {
    socket.emit("round.load", { market_start_ts });
}

function applyOrderSizes(payload) {
    document.getElementById("sizeUpInput").value = String(payload.size_up_usd);
    document.getElementById("sizeDownInput").value = String(payload.size_down_usd);
}

function requestPreviews() {
    if (!state.session?.loaded || state.session.round_ended) return;
    const size_up_usd = Number(document.getElementById("sizeUpInput").value) || 0;
    const size_down_usd = Number(document.getElementById("sizeDownInput").value) || 0;
    emitAck("order.preview", { size_up_usd, size_down_usd }).then((res) => {
        applyButtonPreviews(state.tick, res.previews);
    }).catch(() => {});
}

function showRoundDays() {
    renderRoundPickerDays(state.roundDays, openRoundDay);
}

function openRoundDay(dayUtc) {
    const cached = state.loadedRoundDays[dayUtc];
    if (cached) {
        renderRoundPickerRounds(dayUtc, cached, showRoundDays, loadRound);
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
        renderRoundPickerRounds(dayUtc, res.rounds, showRoundDays, loadRound);
    }).catch((e) => alert(e.message));
}

socket.on("bootstrap", (payload) => {
    state.roundDays = payload.round_days || [];
    showRoundDays();
    applyOrderSizes({ size_up_usd: payload.default_order_size_usd, size_down_usd: payload.default_order_size_usd });
});

socket.on("session", (payload) => {
    state.session = payload;
    if (!payload.round_ended) document.getElementById("outcomeBadge").classList.remove("show");
    if (payload.loaded && payload.market_start_ts !== state.activeRoundTs) {
        state.activeRoundTs = payload.market_start_ts;
        state.syncSizesOnNextOrders = true;
    }
    renderTick(state);
});

socket.on("tick", (payload) => { state.tick = payload; renderTick(state); requestPreviews(); });

socket.on("orders", (payload) => {
    state.orders = payload;
    if (state.syncSizesOnNextOrders) {
        applyOrderSizes(payload);
        state.syncSizesOnNextOrders = false;
        requestPreviews();
    }
    renderOrders(payload);
});

socket.on("history", (payload) => {
    state.historyRows = payload.rows || [];
    renderHistory(state.historyRows);
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

socket.on("error", (payload) => alert(payload.message || "error"));


document.getElementById("playBtn").addEventListener("click", () => emitAck("replay.play").catch(alert));
document.getElementById("pauseBtn").addEventListener("click", () => emitAck("replay.pause").catch(alert));

const slider = document.getElementById("timelineSlider");
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
});
slider.addEventListener("pointerup", () => {
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
    const header = ["Date","Time","Direction","Size","Entry Sec","Exit Sec","Entry BTC","Exit BTC","Result","PnL"];
    const lines = [header.join(",")];
    rows.forEach((r) => lines.push([
        r.date_utc, r.time_utc, r.direction, r.size_usd, r.entry_sec, r.exit_sec ?? "",
        r.entry_btc ?? "", r.exit_btc ?? "", r.result ?? "", r.pnl_usd ?? "",
    ].join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "dashv2-history.csv";
    a.click();
});

renderStakeButtons();
initChart(document.getElementById("chartContainer"));
layoutReplayScale();
window.addEventListener("resize", layoutReplayScale);

document.getElementById("openOrdersList").addEventListener("click", (e) => {
    const btn = e.target.closest(".close-order-btn");
    if (!btn || btn.disabled) return;
    emitAck("order.close", { order_id: btn.dataset.id }).catch(alert);
});
