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


function money(v, decimals = 2) {
    if (v == null || Number.isNaN(v)) return "—";
    const n = Number(v.toFixed(decimals));
    if (n < 0) return `-$${Math.abs(n).toFixed(decimals)}`;
    if (n > 0) return `+$${n.toFixed(decimals)}`;
    return `$${n.toFixed(decimals)}`;
}


function pct(v) {
    if (v == null || Number.isNaN(v)) return "—";
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toFixed(1)}%`;
}


function signedStatClass(v) {
    if (v == null || Number.isNaN(v) || v === 0) return "";
    return v > 0 ? "account-stat-pos" : "account-stat-neg";
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
    const total = days.reduce((n, d) => n + d.count, 0);
    menu.innerHTML = `
        <li><h6 class="dropdown-header">Rounds: ${total}</h6></li>
        ${days.map((d) => `
        <li><button class="dropdown-item round-day-btn" type="button" data-day="${d.day_utc}">
            ${d.day_utc}<span class="text-muted-app ms-1">(${d.count})</span>
            <i class="bi bi-chevron-right float-end opacity-50"></i>
        </button></li>`).join("")}`;
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


function orderDetailStatic(o) {
    return `Entry $${o.entry_btc?.toFixed(0) ?? "—"} · Sec ${o.entry_sec} · Quote ${o.best_ask_c}c`;
}


function orderDetailPnl(o) {
    if (o.profit_if_win_usd == null) return "";
    return ` · Win $${o.profit_if_win_usd.toFixed(2)}`;
}


function sourceBadge(source) {
    const src = source === "bot" ? "bot" : "user";
    return `<span class="badge history-side-badge order-source-badge">${src}</span>`;
}


function orderRowHtml(o) {
    const sideCls = o.side === "Up" ? "order-side-up" : "order-side-down";
    const rowCls = o.side === "Down" ? "order-row down" : "order-row";
    const { text: mtm, cls: badgeCls } = orderMtmBadge(o);
    return `<div class="${rowCls} rounded p-2 mb-2 d-flex align-items-center justify-content-between" data-order-id="${o.id}"><div><strong class="${sideCls}">${o.side.toUpperCase()}</strong><span class="text-muted-app mx-2">·</span>${sourceBadge(o.source)}<span class="text-muted-app mx-2">·</span><span>$${o.size_usd.toFixed(2)}</span><div class="text-muted-app order-detail-line"><span class="order-detail-static">${orderDetailStatic(o)}</span><span class="order-detail-pnl">${orderDetailPnl(o)}</span></div></div><div class="d-flex align-items-center gap-2"><span class="badge history-side-badge order-mtm-badge ${badgeCls}">${mtm}</span><button class="btn btn-sm btn-outline-secondary cancel-order-btn" data-id="${o.id}" type="button">Cancel</button><button class="btn btn-sm btn-outline-light close-order-btn" data-id="${o.id}" type="button" ${o.close_enabled ? "" : "disabled"}>Close</button></div></div>`;
}


function patchOrderRow(row, o) {
    const { text: mtm, cls: badgeCls } = orderMtmBadge(o);
    const badge = row.querySelector(".order-mtm-badge");
    badge.textContent = mtm;
    badge.className = `badge history-side-badge order-mtm-badge ${badgeCls}`;
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


function historyBetRow(r, hidden) {
    const entryQ = r.entry_quote_c != null ? `${r.entry_quote_c}c` : "—";
    const exitQ = r.exit_quote_c != null ? `${r.exit_quote_c}c` : "—";
    const entry = `${entryQ} / ${r.entry_sec}s`;
    const exit = r.exit_sec != null ? `${exitQ} / ${r.exit_sec}s` : "—";
    const hiddenCls = hidden ? " history-bet-row-hidden" : "";
    return `<tr class="history-bet-row${hiddenCls}" data-session-id="${r.session_id || ""}"><td></td><td></td><td>${r.date_utc}</td><td>${r.time_utc}</td><td>${sourceBadge(r.source)}</td><td>${sideBadge(r.direction)}</td><td>${sideBadge(r.outcome)}</td><td>$${r.size_usd.toFixed(2)}</td><td>${entry}</td><td>${exit}</td>${valCell(r.final_pnl_usd)}${valCell(r.pnl_usd)}</tr>`;
}


function sumField(rows, key) {
    let total = 0;
    let any = false;
    for (const r of rows) {
        const v = r[key];
        if (v == null) continue;
        total += v;
        any = true;
    }
    return any ? total : null;
}


function groupHistoryRows(rows) {
    const groups = new Map();
    for (const r of rows) {
        const sid = r.session_id || `${r.market_start_ts}:${r.date_utc}:${r.time_utc}:${groups.size}`;
        if (!groups.has(sid)) groups.set(sid, []);
        groups.get(sid).push(r);
    }
    const out = [];
    for (const [sessionId, bets] of groups) {
        bets.sort((a, b) => (b.entry_sec ?? 0) - (a.entry_sec ?? 0));
        out.push({
            sessionId,
            market_start_ts: bets[0].market_start_ts,
            session_date_utc: bets[0].session_date_utc,
            session_time_utc: bets[0].session_time_utc,
            session_started_at_utc: bets[0].session_started_at_utc || "",
            session_sort_ts: bets[0].session_sort_ts || 0,
            date_utc: bets[0].date_utc,
            time_utc: bets[0].time_utc,
            outcome: bets[0].outcome,
            size_usd: bets.reduce((s, b) => s + b.size_usd, 0),
            final_pnl_usd: sumField(bets, "final_pnl_usd"),
            pnl_usd: sumField(bets, "pnl_usd"),
            bets,
        });
    }
    out.sort((a, b) => (b.session_sort_ts - a.session_sort_ts) || b.sessionId.localeCompare(a.sessionId));
    return out;
}


const expandedHistorySessions = new Set();


function historySessionRow(g) {
    const expanded = expandedHistorySessions.has(g.sessionId);
    const icon = expanded ? "−" : "+";
    const betCount = g.bets.length;
    const countLabel = betCount > 1 ? `<span class="history-session-count">${betCount}</span>` : "";
    const sessionLabel = g.session_date_utc === "—" ? "—" : `${g.session_date_utc} ${g.session_time_utc}`;
    return `<tr class="history-session-row${expanded ? " history-session-row-expanded" : ""}" data-session-id="${g.sessionId}"><td class="history-session-datetime">${sessionLabel}${countLabel}</td><td class="history-toggle-col"><span class="history-toggle-icon" aria-hidden="true">${icon}</span></td><td class="text-muted-app">—</td><td class="text-muted-app">—</td><td class="text-muted-app">—</td><td class="text-muted-app">—</td><td class="text-muted-app">—</td><td>$${g.size_usd.toFixed(2)}</td><td class="text-muted-app">—</td><td class="text-muted-app">—</td>${valCell(g.final_pnl_usd, "history-session-val")}${valCell(g.pnl_usd, "history-session-val")}</tr>`;
}


export function renderHistory(rows) {
    const groups = groupHistoryRows(rows);
    const html = [];
    for (const g of groups) {
        html.push(historySessionRow(g));
        const hidden = !expandedHistorySessions.has(g.sessionId);
        for (const r of g.bets) html.push(historyBetRow(r, hidden));
    }
    $("historyTableBody").innerHTML = html.join("");
}


export function toggleHistorySession(sessionId) {
    if (expandedHistorySessions.has(sessionId)) expandedHistorySessions.delete(sessionId);
    else expandedHistorySessions.add(sessionId);
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
    renderBotSelect(state);
}


export function renderBotSelect(state) {
    const bots = state.bots || [];
    const selected = state.selectedBotId || "";
    const attachOk = state.session?.bot_attach_allowed ?? state.botAttachAllowed ?? true;
    const select = $("botSelect");
    select.disabled = !attachOk;
    select.innerHTML = [`<option value="">None</option>`]
        .concat(bots.map((b) => `<option value="${b.id}"${b.id === selected ? " selected" : ""}>${b.name}</option>`))
        .join("");
    const sw = $("botActiveSwitch");
    sw.disabled = !selected;
    sw.checked = !!(selected && state.botActive);
    const label = $("botStatusLabel");
    if (!selected) label.textContent = "";
    else label.textContent = state.botActive ? "READY" : "PAUSED";
}


function statBlock(label, value, valueClass = "") {
    const cls = valueClass ? `account-stat-value ${valueClass}` : "account-stat-value";
    return `<div><div class="account-stat-label">${label}</div><div class="${cls}">${value}</div></div>`;
}


export function renderAccountSummary(account) {
    const body = $("accountSummaryBody");
    if (!account) {
        body.innerHTML = `<p class="text-muted-app mb-0 tiny">Crea o seleziona un account per vedere i dati.</p>`;
        return;
    }
    const note = account.note ? `<div class="mt-2 tiny text-muted-app">${account.note}</div>` : "";
    const ordersValue = `${account.order_count}=${account.wins}+${account.losses}`;
    body.innerHTML = `
        <div class="account-summary-grid">
            ${statBlock("Initial balance", money(account.initial_balance_usd))}
            ${statBlock("Current balance", money(account.current_balance_usd))}
            ${statBlock("ORDERS=W+L", ordersValue)}
            ${statBlock("Total stake", money(account.total_staked_usd, 0))}
            ${statBlock("Avg stake", money(account.avg_stake_usd, 0))}
            ${statBlock("Realized PnL", money(account.realized_pnl_usd), signedStatClass(account.realized_pnl_usd))}
            ${statBlock("Gain %", pct(account.gain_pct), signedStatClass(account.gain_pct))}
            ${statBlock("Win rate", pct(account.win_rate_pct), signedStatClass(account.win_rate_pct))}
        </div>${note}`;
}


export function renderOutcome(roundEnd) {
    $("orderOutcome").textContent = roundEnd.outcome_label;
}


export function setDisconnectBanner(show) {
    $("disconnectBanner").classList.toggle("show", show);
}
