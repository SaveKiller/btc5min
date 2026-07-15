/** Aggiornamento DOM dashboard v38. */

const $ = (id) => document.getElementById(id);


function formatMmSs(sec) {
    const mm = Math.floor(sec / 60);
    const ss = sec % 60;
    return `${mm}:${String(ss).padStart(2, "0")}`;
}


const TIMELINE_THUMB_PX = 16;


function timelineThumbLeft(pct) {
    return `calc(${pct * 100}% + ${(0.5 - pct) * TIMELINE_THUMB_PX}px)`;
}


export function layoutReplayScale() {
    const scale = document.querySelector(".replay-scale");
    if (!scale) return;
    const max = Number($("timelineSlider").max);
    scale.querySelectorAll("span").forEach((span) => {
        const sec = Number(span.textContent);
        const pct = (max - sec) / max;
        span.style.left = timelineThumbLeft(pct);
    });
}


function updateTimelineSecLabel(sec, progress) {
    const slider = $("timelineSlider");
    const label = $("timelineSecLabel");
    label.textContent = String(sec);
    const min = Number(slider.min);
    const max = Number(slider.max);
    const pct = (progress - min) / (max - min);
    label.style.left = timelineThumbLeft(pct);
}


export function renderStakeButtons() {
    const amounts = [1, 10, 20, 50, 100];
    document.querySelectorAll(".stake[data-side]").forEach((wrap) => {
        wrap.innerHTML = amounts.map((n) => `<button class="btn btn-sm btn-outline-secondary stake-btn" type="button" data-amount="${n}">$${n}</button>`).join("");
    });
}


export function renderRoundPickerDays(days, onDaySelect) {
    const menu = $("roundPickerMenu");
    menu.innerHTML = days.map((d) => `
        <li><button class="dropdown-item round-day-btn" type="button" data-day="${d.day_utc}">
            ${d.day_utc}<span class="text-muted-app ms-1">(${d.count})</span>
            <i class="bi bi-chevron-right float-end opacity-50"></i>
        </button></li>`).join("");
    menu.querySelectorAll(".round-day-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            onDaySelect(btn.dataset.day);
        });
    });
}


export function renderRoundPickerHours(dayUtc, hours, onBack, onHourSelect) {
    const menu = $("roundPickerMenu");
    menu.innerHTML = `
        <li><button class="dropdown-item round-picker-back" type="button"><i class="bi bi-chevron-left me-1"></i>Giorni</button></li>
        <li><hr class="dropdown-divider"></li>
        <li><h6 class="dropdown-header">${dayUtc} UTC</h6></li>
        ${hours.map((h) => `
        <li><button class="dropdown-item round-hour-btn" type="button" data-hour="${h.hour_utc}">
            ${h.hour_utc}<span class="text-muted-app ms-1">(${h.count})</span>
            <i class="bi bi-chevron-right float-end opacity-50"></i>
        </button></li>`).join("")}`;
    menu.querySelector(".round-picker-back").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        onBack();
    });
    menu.querySelectorAll(".round-hour-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            onHourSelect(btn.dataset.hour);
        });
    });
}


export function renderRoundPickerRounds(dayUtc, hourUtc, rounds, onBack, onSelect) {
    const menu = $("roundPickerMenu");
    const items = rounds.map((r) => {
        const cls = r.valid ? "" : "disabled";
        const title = r.valid ? "" : ` title="${r.reason || "invalid"}"`;
        return `<li><button class="dropdown-item ${cls}" type="button" data-ts="${r.market_start_ts}"${title}>${r.label}</button></li>`;
    }).join("");
    menu.innerHTML = `
        <li><button class="dropdown-item round-picker-back" type="button"><i class="bi bi-chevron-left me-1"></i>Orari</button></li>
        <li><hr class="dropdown-divider"></li>
        <li><h6 class="dropdown-header">${dayUtc} · ${hourUtc} UTC</h6></li>
        ${items}`;
    menu.querySelector(".round-picker-back").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        onBack();
    });
    menu.querySelectorAll("button[data-ts]").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (btn.classList.contains("disabled")) return;
            onSelect(Number(btn.dataset.ts));
        });
    });
}


function profitPctText(prev, sizeUsd) {
    if (!prev) return "—";
    const profit = prev.profit_if_win_usd ?? 0;
    if (sizeUsd <= 0) return "0%";
    if (prev.roi_if_win != null) return `${Math.round(prev.roi_if_win * 100)}%`;
    return `${Math.round((profit / sizeUsd) * 100)}%`;
}


export function applyButtonPreviews(tick, previews) {
    const prev = previews || {};
    const sizeUp = Number($("sizeUpInput").value) || 0;
    const sizeDown = Number($("sizeDownInput").value) || 0;
    if (prev.Up) {
        $("upAskLabel").textContent = `${prev.Up.best_ask_c}¢`;
        $("upProfitLabel").textContent = `$${Math.round(prev.Up.profit_if_win_usd)}`;
        $("upProfitPctLabel").textContent = profitPctText(prev.Up, sizeUp);
    } else {
        $("upAskLabel").textContent = tick?.up_ask_c != null ? `${tick.up_ask_c}¢` : "—";
        $("upProfitLabel").textContent = "—";
        $("upProfitPctLabel").textContent = "—";
    }
    if (prev.Down) {
        $("downAskLabel").textContent = `${prev.Down.best_ask_c}¢`;
        $("downProfitLabel").textContent = `$${Math.round(prev.Down.profit_if_win_usd)}`;
        $("downProfitPctLabel").textContent = profitPctText(prev.Down, sizeDown);
    } else {
        $("downAskLabel").textContent = tick?.down_ask_c != null ? `${tick.down_ask_c}¢` : "—";
        $("downProfitLabel").textContent = "—";
        $("downProfitPctLabel").textContent = "—";
    }
}


function signalCardHtml(side, tick) {
    const dwinA = tick?.dwin_a;
    const dwinB = tick?.dwin_b;
    const rq = tick?.rq ?? "—";
    const rs = tick?.rs ?? "—";
    const sideLabel = side.toUpperCase();
    const aPct = dwinA?.p_win_pct != null ? `${dwinA.p_win_pct}%` : "—";
    const aN = dwinA?.n != null ? `n=${dwinA.n}` : "n=—";
    const bPct = dwinB?.p_win_pct != null ? `${dwinB.p_win_pct}%` : "—";
    return `<div class="row g-0"><div class="col-6 model-split p-2"><div class="tiny text-muted-app">Model A · ${aN}</div><div class="signal-value text-success">${aPct} <span class="fs-6 text-muted-app">${sideLabel}</span></div><div class="model-details">Rq ${rq}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Rs ${rs}</div></div><div class="col-6 model-split p-2"><div class="tiny text-muted-app">Model B</div><div class="signal-value text-success">${bPct} <span class="fs-6 text-muted-app">${sideLabel}</span></div><div class="model-details">Rq ${rq}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Rs ${rs}</div></div></div>`;
}


export function renderTick(state) {
    const tick = state.tick;
    const session = state.session;
    if (session?.loaded) {
        $("replayTimestamp").textContent = session.replay_timestamp;
        $("timelineSlider").value = String(session.progress);
        updateTimelineSecLabel(session.sec, session.progress);
        $("refPtb").textContent = Math.round(session.ptb_chainlink).toLocaleString("en-US");
        $("orderSecToEnd").textContent = String(session.sec);
        if (!session.round_ended) $("orderOutcome").textContent = "---";
        $("refCountdown").textContent = formatMmSs(session.sec);
    }
    if (tick?.chainlink_btc != null) {
        $("btcPrice").textContent = `${Math.round(tick.chainlink_btc).toLocaleString("en-US")} $`;
    } else {
        $("btcPrice").textContent = "—";
    }
    const delta = tick?.delta_usd;
    if (delta != null) {
        const neg = delta < 0 ? Math.abs(delta) : 0;
        const pos = delta > 0 ? delta : 0;
        $("refNeg").textContent = neg ? `-${neg}` : "0";
        $("refPos").textContent = pos ? `+${pos}` : "0";
        const negFill = Math.min(100, Math.max(0, (neg / 120) * 100));
        const posFill = Math.min(100, Math.max(0, (pos / 120) * 100));
        $("refNegFill").style.width = `${negFill}%`;
        $("refPosFill").style.width = `${posFill}%`;
    }
    $("upSignals").innerHTML = signalCardHtml("UP", tick);
    $("downSignals").innerHTML = signalCardHtml("DOWN", tick);
    const prev = tick?.previews || {};
    applyButtonPreviews(tick, prev);
    const tradable = tick?.tradable && session?.tradable;
    $("buyUpBtn").disabled = !tradable;
    $("buyDownBtn").disabled = !tradable;
}


function orderRowHtml(o) {
    const sideCls = o.side === "Up" ? "text-success" : "text-danger";
    const rowCls = o.side === "Down" ? "order-row down" : "order-row";
    const mtm = o.mtm_available && o.mtm_usd != null ? `$${o.mtm_usd >= 0 ? "+" : ""}${o.mtm_usd.toFixed(2)}` : "Pending";
    const badgeCls = o.mtm_available && o.mtm_usd != null ? (o.mtm_usd >= 0 ? "text-bg-success" : "text-bg-danger") : "text-bg-secondary";
    const win = o.profit_if_win_usd != null ? ` · WIN $${o.profit_if_win_usd.toFixed(2)}` : "";
    const mtmLine = o.mtm_available && o.mtm_usd != null ? ` · MTM $${o.mtm_usd.toFixed(2)}` : "";
    return `<div class="${rowCls} rounded p-2 mb-2 d-flex align-items-center justify-content-between" data-order-id="${o.id}"><div><strong class="${sideCls}">${o.side.toUpperCase()}</strong><span class="text-muted-app mx-2">·</span><span>$${o.size_usd.toFixed(2)}</span><div class="tiny text-muted-app">Entry $${o.entry_btc?.toFixed(0) ?? "—"} · sec ${o.entry_sec} · Quote ${o.best_ask_c}c · Payout $${o.payout_if_win_usd?.toFixed(2) ?? "—"}${mtmLine}${win}</div></div><div class="d-flex align-items-center gap-2"><span class="badge order-mtm-badge ${badgeCls}">${mtm}</span><button class="btn btn-sm btn-outline-light close-order-btn" data-id="${o.id}" type="button" ${o.close_enabled ? "" : "disabled"}>Close</button></div></div>`;
}


function patchOrderRow(row, o) {
    const mtm = o.mtm_available && o.mtm_usd != null ? `$${o.mtm_usd >= 0 ? "+" : ""}${o.mtm_usd.toFixed(2)}` : "Pending";
    const badgeCls = o.mtm_available && o.mtm_usd != null ? (o.mtm_usd >= 0 ? "text-bg-success" : "text-bg-danger") : "text-bg-secondary";
    const badge = row.querySelector(".order-mtm-badge");
    badge.textContent = mtm;
    badge.className = `badge order-mtm-badge ${badgeCls}`;
    const btn = row.querySelector(".close-order-btn");
    btn.disabled = !o.close_enabled;
}


export function renderOrders(orders) {
    $("openOrdersCount").textContent = String(orders.open.length);
    const list = $("openOrdersList");
    const open = orders.open;
    if (!open.length) {
        list.dataset.orderIds = "";
        list.innerHTML = "";
        return;
    }
    const ids = open.map((o) => o.id).join(",");
    if (list.dataset.orderIds !== ids) {
        list.dataset.orderIds = ids;
        list.innerHTML = open.map(orderRowHtml).join("");
        return;
    }
    open.forEach((o) => {
        const row = list.querySelector(`[data-order-id="${o.id}"]`);
        if (row) patchOrderRow(row, o);
    });
}


export function renderHistory(rows) {
    $("historyTableBody").innerHTML = rows.map((r) => {
        const dirCls = r.direction === "Up" ? "text-bg-success" : "text-bg-danger";
        const resCls = r.result === "won" ? "text-success" : (r.result === "lost" ? "text-danger" : "text-muted-app");
        const pnlCls = (r.pnl_usd ?? 0) >= 0 ? "text-success" : "text-danger";
        const pnl = r.pnl_usd != null ? `${r.pnl_usd >= 0 ? "+" : ""}$${r.pnl_usd.toFixed(2)}` : "—";
        const entry = r.entry_btc != null ? Math.round(r.entry_btc) : "—";
        const exit = r.exit_btc != null ? Math.round(r.exit_btc) : "—";
        return `<tr><td>${r.date_utc}</td><td>${r.time_utc}</td><td><span class="badge ${dirCls}">${r.direction.toUpperCase()}</span></td><td>$${r.size_usd.toFixed(2)}</td><td>${r.entry_sec}</td><td>${r.exit_sec ?? "—"}</td><td>${entry} / ${exit}</td><td><span class="${resCls}">${r.result || "—"}</span></td><td class="text-end ${pnlCls} fw-semibold">${pnl}</td></tr>`;
    }).join("");
}


export function renderOutcome(roundEnd) {
    $("orderOutcome").textContent = roundEnd.outcome_label;
}


export function setDisconnectBanner(show) {
    $("disconnectBanner").classList.toggle("show", show);
}
