/** Aggiornamento DOM dashboard v38. */

const $ = (id) => document.getElementById(id);


function formatMmSs(sec) {
    const mm = Math.floor(sec / 60);
    const ss = sec % 60;
    return `${mm}:${String(ss).padStart(2, "0")}`;
}


function formatRoundClockUtc(market_start_ts, sec) {
    const d = new Date((market_start_ts + 300 - sec) * 1000);
    const h = String(d.getUTCHours()).padStart(2, "0");
    const m = String(d.getUTCMinutes()).padStart(2, "0");
    const s = String(d.getUTCSeconds()).padStart(2, "0");
    return `${h}:${m}:${s}`;
}


function money(v) {
    if (v == null || Number.isNaN(v)) return "—";
    const sign = v >= 0 ? "+" : "";
    return `${sign}$${Math.abs(v).toFixed(2)}`;
}


function pct(v) {
    if (v == null || Number.isNaN(v)) return "—";
    const sign = v >= 0 ? "+" : "";
    return `${sign}${v.toFixed(1)}%`;
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


const UTC_HOUR_MARKETS = [
    "Sydney, Tokyo", "Sydney, Tokyo", "Sydney, Tokyo", "Sydney, Tokyo", "Sydney, Tokyo", "Sydney, Tokyo",
    "Tokyo", "Tokyo, Londra", "Tokyo, Londra", "Londra", "Londra", "Londra", "Londra",
    "Londra, New York", "Londra, New York", "Londra, New York",
    "New York", "New York", "New York", "New York", "New York",
    "Sydney, New York", "Sydney", "Sydney",
];


function marketsForHourUtc(hourUtc) {
    return UTC_HOUR_MARKETS[parseInt(hourUtc.split(":")[0], 10)] ?? "";
}


export function renderRoundPickerDays(days, onDaySelect) {
    const menu = $("roundPickerMenu");
    menu.classList.remove("round-picker-rounds", "round-picker-hours");
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
    menu.classList.remove("round-picker-rounds");
    menu.classList.add("round-picker-hours");
    menu.innerHTML = `
        <li><button class="dropdown-item round-picker-back" type="button"><i class="bi bi-chevron-left me-1"></i>Giorni</button></li>
        <li><hr class="dropdown-divider"></li>
        <li><h6 class="dropdown-header">${dayUtc} UTC</h6></li>
        ${hours.map((h) => `
        <li><button class="dropdown-item round-hour-btn" type="button" data-hour="${h.hour_utc}">
            <span class="round-hour-time">${h.hour_utc}<span class="text-muted-app ms-1">(${h.count})</span></span>
            <span class="round-hour-markets">${marketsForHourUtc(h.hour_utc)}</span>
            <i class="bi bi-chevron-right round-hour-chevron"></i>
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
    menu.classList.remove("round-picker-hours");
    menu.classList.add("round-picker-rounds");
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


function dwinPctForSide(sideLabel, refSide, rawPct) {
    if (rawPct == null || refSide == null) return null;
    const side = sideLabel === "UP" ? "Up" : "Down";
    return side === refSide ? rawPct : 100 - rawPct;
}


function riskForSide(sideLabel, tick) {
    const key = sideLabel === "UP" ? "Up" : "Down";
    const r = tick?.risk?.[key];
    return { rq: r?.rq ?? "—", rs: r?.rs ?? "—" };
}


function sideRiskHtml(rq, rs) {
    const rqNum = typeof rq === "number" ? rq : null;
    const rsNum = typeof rs === "number" ? rs : null;
    const rqTxt = rqNum != null ? String(rqNum) : "—";
    const rsTxt = rsNum != null ? String(rsNum) : "—";
    if (rqNum == null || rsNum == null) {
        return `<div class="side-risk px-2 pb-2">Rq ${rqTxt}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Rs ${rsTxt}</div>`;
    }
    const diff = Math.abs(rqNum - rsNum);
    if (diff < 2) {
        return `<div class="side-risk px-2 pb-2">Rq ${rqTxt}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Rs ${rsTxt}</div>`;
    }
    const rqLow = rqNum < rsNum;
    const rqClass = rqLow ? "risk-val-low" : "risk-val-high";
    const rsClass = rqLow ? "risk-val-high" : "risk-val-low";
    return `<div class="side-risk side-risk-mismatch px-2 pb-2"><span class="${rqClass}">Rq ${rqTxt}</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span class="${rsClass}">Rs ${rsTxt}</span></div>`;
}


function signalCardHtml(side, tick) {
    const refSide = tick?.dwin_ref_side;
    const dwinA = tick?.dwin_a;
    const dwinB = tick?.dwin_b;
    const { rq, rs } = riskForSide(side, tick);
    const sideLabel = side.toUpperCase();
    const aPctVal = dwinPctForSide(side, refSide, dwinA?.p_win_pct);
    const bPctVal = dwinPctForSide(side, refSide, dwinB?.p_win_pct);
    const aPct = aPctVal != null ? `${aPctVal}%` : "—";
    const aN = dwinA?.n != null ? `n=${dwinA.n}` : "n=—";
    const bPct = bPctVal != null ? `${bPctVal}%` : "—";
    return `<div class="row g-0"><div class="col-6 model-split p-2"><div class="tiny text-muted-app">Model A · ${aN}</div><div class="signal-value text-success">${aPct} <span class="signal-side-label text-muted-app">${sideLabel}</span></div></div><div class="col-6 model-split p-2"><div class="tiny text-muted-app">Model B</div><div class="signal-value text-success">${bPct} <span class="signal-side-label text-muted-app">${sideLabel}</span></div></div></div>${sideRiskHtml(rq, rs)}`;
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
        $("orderRoundTime").textContent = formatRoundClockUtc(session.market_start_ts, session.sec);
        if (!session.round_ended) $("orderOutcome").textContent = "---";
        $("refCountdown").textContent = formatMmSs(session.sec);
    }
    if (tick?.chainlink_btc != null) {
        const btc = Math.round(tick.chainlink_btc).toLocaleString("en-US");
        $("btcPrice").textContent = `${btc} $`;
        $("orderBtcPrice").textContent = btc;
    } else {
        $("btcPrice").textContent = "—";
        $("orderBtcPrice").textContent = "—";
    }
    const delta = tick?.delta_usd;
    const deltaEl = $("orderDelta");
    if (delta == null) {
        deltaEl.textContent = "---";
        deltaEl.classList.remove("delta-pos", "delta-neg");
    } else {
        deltaEl.textContent = delta > 0 ? `+${delta.toLocaleString("en-US")}` : delta.toLocaleString("en-US");
        deltaEl.classList.toggle("delta-pos", delta > 0);
        deltaEl.classList.toggle("delta-neg", delta < 0);
    }
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
    const tradable = tick?.tradable && (
        session?.tradable || (state.scrubbing && !session?.round_ended && session?.sec >= 1)
    );
    $("buyUpBtn").disabled = !tradable;
    $("buyDownBtn").disabled = !tradable;
}


function orderMtmBadge(o) {
    if (o.mtm_usd == null) return { text: "Pending", cls: "order-mtm-pending" };
    return {
        text: `$${o.mtm_usd >= 0 ? "+" : ""}${o.mtm_usd.toFixed(2)}`,
        cls: o.mtm_usd >= 0 ? "history-up" : "history-down",
    };
}


function orderDetailLine(o) {
    const win = o.profit_if_win_usd != null ? ` · Win $${o.profit_if_win_usd.toFixed(2)}` : "";
    return `Entry $${o.entry_btc?.toFixed(0) ?? "—"} · Sec ${o.entry_sec} · Quote ${o.best_ask_c}c${win}`;
}


function orderRowHtml(o) {
    const sideCls = o.side === "Up" ? "order-side-up" : "order-side-down";
    const rowCls = o.side === "Down" ? "order-row down" : "order-row";
    const { text: mtm, cls: badgeCls } = orderMtmBadge(o);
    return `<div class="${rowCls} rounded p-2 mb-2 d-flex align-items-center justify-content-between" data-order-id="${o.id}"><div><strong class="${sideCls}">${o.side.toUpperCase()}</strong><span class="text-muted-app mx-2">·</span><span>$${o.size_usd.toFixed(2)}</span><div class="text-muted-app order-detail-line">${orderDetailLine(o)}</div></div><div class="d-flex align-items-center gap-2"><span class="badge history-side-badge order-mtm-badge ${badgeCls}">${mtm}</span><button class="btn btn-sm btn-outline-secondary cancel-order-btn" data-id="${o.id}" type="button">Cancel</button><button class="btn btn-sm btn-outline-light close-order-btn" data-id="${o.id}" type="button" ${o.close_enabled ? "" : "disabled"}>Close</button></div></div>`;
}


function patchOrderRow(row, o) {
    const { text: mtm, cls: badgeCls } = orderMtmBadge(o);
    const badge = row.querySelector(".order-mtm-badge");
    badge.textContent = mtm;
    badge.className = `badge history-side-badge order-mtm-badge ${badgeCls}`;
    const detail = row.querySelector(".order-detail-line");
    if (detail) detail.textContent = orderDetailLine(o);
    const btn = row.querySelector(".close-order-btn");
    btn.disabled = !o.close_enabled;
}


export function renderOrders(orders) {
    $("openOrdersCount").textContent = String(orders.open.length);
    const list = $("openOrdersList");
    const open = orders.open;
    if (!open.length) {
        list.dataset.orderIds = "";
        list.innerHTML = `<div class="open-orders-placeholder">NO ORDERS</div>`;
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


function sideBadge(side) {
    if (!side || side === "unknown") return "—";
    const cls = side === "Up" ? "history-up" : "history-down";
    return `<span class="badge history-side-badge ${cls}">${side.toUpperCase()}</span>`;
}


function valCell(v, clsBase = "") {
    if (v == null) return `<td class="text-end ${clsBase}">—</td>`;
    const cls = v >= 0 ? "history-val-pos" : "history-val-neg";
    return `<td class="text-end ${clsBase} ${cls} fw-semibold">${v >= 0 ? "+" : ""}$${v.toFixed(2)}</td>`;
}


export function renderHistory(rows) {
    $("historyTableBody").innerHTML = rows.map((r) => {
        const entryQ = r.entry_quote_c != null ? `${r.entry_quote_c}c` : "—";
        const exitQ = r.exit_quote_c != null ? `${r.exit_quote_c}c` : "—";
        const entry = `${entryQ} / ${r.entry_sec}s`;
        const exit = r.exit_sec != null ? `${exitQ} / ${r.exit_sec}s` : "—";
        return `<tr><td>${r.date_utc}</td><td>${r.time_utc}</td><td>${sideBadge(r.direction)}</td><td>${sideBadge(r.outcome)}</td><td>$${r.size_usd.toFixed(2)}</td><td>${entry}</td><td>${exit}</td>${valCell(r.final_pnl_usd)}${valCell(r.pnl_usd)}</tr>`;
    }).join("");
}


export function renderAccounts(state) {
    const accounts = state.accounts || [];
    const activeId = state.activeAccountId;
    const locked = !!state.session?.account_switch_locked;
    const count = accounts.length;
    $("accountCountLabel").textContent = `${count} account${count === 1 ? "" : "s"}`;
    const select = $("accountSelect");
    if (!count) {
        select.innerHTML = `<option value="">Create your first account</option>`;
        select.disabled = true;
    } else {
        select.disabled = locked;
        select.innerHTML = accounts.map((a) => `<option value="${a.id}"${a.id === activeId ? " selected" : ""}>${a.name}</option>`).join("");
    }
    const hasActive = activeId != null;
    $("renameAccountBtn").disabled = !hasActive;
    $("editAccountBtn").disabled = !hasActive;
    $("exportCsvBtn").disabled = !hasActive;
    renderAccountSummary(state.activeAccount);
}


function statBlock(label, value) {
    return `<div><div class="account-stat-label">${label}</div><div class="account-stat-value">${value}</div></div>`;
}


export function renderAccountSummary(account) {
    const body = $("accountSummaryBody");
    if (!account) {
        body.innerHTML = `<p class="text-muted-app mb-0 tiny">Crea o seleziona un account per vedere i dati.</p>`;
        return;
    }
    const note = account.note ? `<div class="mt-2 tiny text-muted-app">${account.note}</div>` : "";
    body.innerHTML = `
        <div class="account-summary-grid">
            ${statBlock("Current balance", money(account.current_balance_usd))}
            ${statBlock("Initial balance", money(account.initial_balance_usd))}
            ${statBlock("Realized PnL", money(account.realized_pnl_usd))}
            ${statBlock("Gain %", pct(account.gain_pct))}
            ${statBlock("Wins", String(account.wins))}
            ${statBlock("Losses", String(account.losses))}
            ${statBlock("Win rate", pct(account.win_rate_pct))}
            ${statBlock("Orders", String(account.order_count))}
            ${statBlock("Total staked", money(account.total_staked_usd))}
            ${statBlock("Avg stake", money(account.avg_stake_usd))}
        </div>${note}`;
}


export function renderOutcome(roundEnd) {
    $("orderOutcome").textContent = roundEnd.outcome_label;
}


export function setDisconnectBanner(show) {
    $("disconnectBanner").classList.toggle("show", show);
}
