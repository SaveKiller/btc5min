/** Aggiornamento DOM dashboard v38. */

const $ = (id) => document.getElementById(id);


export function renderEnginePlugin(pluginId) {
    const el = $("enginePluginLabel");
    if (!el) return;
    const id = pluginId || "replay";
    el.textContent = id === "live" ? "LIVE" : "REPLAY";
}


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
const BAND_EDGE_PAD_PX = 12;


function timelineThumbLeft(pct) {
    return `calc(${pct * 100}% + ${(0.5 - pct) * TIMELINE_THUMB_PX}px)`;
}


export function layoutReplayScale() {
    const scale = document.querySelector(".replay-scale");
    if (!scale) return;
    const max = Number($("timelineSlider").max);
    const spans = [...scale.querySelectorAll(":scope > span")];
    const bySec = new Map();
    spans.forEach((span) => {
        const sec = Number(span.textContent);
        const pct = (max - sec) / max;
        span.style.left = timelineThumbLeft(pct);
        bySec.set(sec, { pct, half: span.offsetWidth / 2 });
    });
    document.querySelectorAll(".replay-scale-band").forEach((band) => {
        const from = bySec.get(Number(band.dataset.from));
        const until = bySec.get(Number(band.dataset.until));
        const inclusive = band.dataset.inclusive === "1";
        const spanPct = until.pct - from.pct;
        const endHalf = inclusive ? until.half : -until.half;
        const startPad = from.pct === 0 ? BAND_EDGE_PAD_PX : 0;
        const endPad = inclusive ? BAND_EDGE_PAD_PX : 0;
        band.style.left = `calc(${from.pct * 100}% + ${(0.5 - from.pct) * TIMELINE_THUMB_PX}px - ${from.half + startPad}px)`;
        band.style.width = `calc(${spanPct * 100}% + ${(from.pct - until.pct) * TIMELINE_THUMB_PX}px + ${from.half + endHalf + startPad + endPad}px)`;
    });
}


function applySecBandClass(el, sec) {
    el.classList.toggle("sec-green", sec <= 240 && sec > 180);
    el.classList.toggle("sec-azure", sec <= 180 && sec > 120);
    el.classList.toggle("sec-warn", sec <= 120 && sec > 60);
    el.classList.toggle("sec-critical", sec <= 60);
}


function updateTimelineSecLabel(sec, progress) {
    const slider = $("timelineSlider");
    const label = $("timelineSecLabel");
    label.textContent = String(sec);
    applySecBandClass(label, sec);
    applySecBandClass(slider, sec);
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
        ${days.map((d) => {
            const cls = d.valid === false ? "disabled" : "";
            const title = d.valid === false ? ' title="missing day"' : "";
            return `<li><button class="dropdown-item round-day-btn ${cls}" type="button" data-day="${d.day_utc}"${title}>
            ${d.day_utc}<span class="text-muted-app ms-1">(${d.count})</span>
            <i class="bi bi-chevron-right float-end opacity-50"></i>
        </button></li>`;
        }).join("")}`;
    menu.querySelectorAll(".round-day-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (btn.classList.contains("disabled")) return;
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
        ${hours.map((h) => {
            const cls = h.valid === false ? "disabled" : "";
            const title = h.valid === false ? ' title="missing hour"' : "";
            return `<li><button class="dropdown-item round-hour-btn ${cls}" type="button" data-hour="${h.hour_utc}"${title}>
            <span class="round-hour-time">${h.hour_utc}<span class="text-muted-app ms-1">(${h.count})</span></span>
            <span class="round-hour-markets">${marketsForHourUtc(h.hour_utc)}</span>
            <i class="bi bi-chevron-right round-hour-chevron"></i>
        </button></li>`;
        }).join("")}`;
    menu.querySelector(".round-picker-back").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        onBack();
    });
    menu.querySelectorAll(".round-hour-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (btn.classList.contains("disabled")) return;
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
    if (rqNum === 9 && rsNum === 9) {
        return `<div class="side-risk side-risk-blank px-2 pb-2" aria-hidden="true">Rq 9&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Rs 9</div>`;
    }
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
        const secEl = $("orderSecToEnd");
        secEl.textContent = String(session.sec);
        applySecBandClass(secEl, session.sec);
        $("orderRoundTime").textContent = formatRoundClockUtc(session.market_start_ts, session.sec);
        if (!session.round_ended) $("orderOutcome").textContent = "---";
        const countdown = $("refCountdown");
        countdown.textContent = formatMmSs(session.sec);
        applySecBandClass(countdown, session.sec);
    }
    const liq2 = tick?.liq2_ask_usd;
    $("orderLiq2").textContent = liq2 != null ? `$${Math.round(liq2).toLocaleString("en-US")}` : "—";
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
    const sid = escapeHtml(r.session_id || "");
    return `<tr class="history-bet-row${hiddenCls}" data-session-id="${sid}"><td class="history-bet-session-id" title="${sid}">${sid}</td><td></td><td></td><td></td><td>${sourceBadge(r.source)}</td><td>${sideBadge(r.direction)}</td><td>${sideBadge(r.outcome)}</td><td>$${r.size_usd.toFixed(2)}</td><td>${entry}</td><td>${exit}</td>${valCell(r.final_pnl_usd)}${valCell(r.pnl_usd)}</tr>`;
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


/** Capitale iniettato nella sessione: wallet riusa solo la size (non i profitti); le perdite riducono il ritorno. */
export function sessionCapitalSizeUsd(bets) {
    const events = [];
    for (const b of bets) {
        const size = Number(b.size_usd);
        events.push({ kind: "open", sec: Number(b.entry_sec), size });
        if (b.exit_sec != null) {
            const pnl = b.pnl_usd == null ? 0 : Number(b.pnl_usd);
            events.push({ kind: "close", sec: Number(b.exit_sec), size, pnl });
        }
    }
    // Cronologia: sec più alto = prima; a parità chiudi prima di aprire (capitale liberato).
    events.sort((a, b) => {
        if (b.sec !== a.sec) return b.sec - a.sec;
        if (a.kind === b.kind) return 0;
        return a.kind === "close" ? -1 : 1;
    });
    let wallet = 0;
    let injected = 0;
    for (const e of events) {
        if (e.kind === "open") {
            if (wallet >= e.size) wallet -= e.size;
            else {
                injected += e.size - wallet;
                wallet = 0;
            }
        } else {
            wallet += e.size + Math.min(0, e.pnl);
        }
    }
    return injected;
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
            size_usd: sessionCapitalSizeUsd(bets),
            final_pnl_usd: sumField(bets, "final_pnl_usd"),
            pnl_usd: sumField(bets, "pnl_usd"),
            bets,
        });
    }
    out.sort((a, b) => (b.session_sort_ts - a.session_sort_ts) || b.sessionId.localeCompare(a.sessionId));
    return out;
}


const expandedHistorySessions = new Set();


function historySessionRow(g, expanded, agentSessionId) {
    const icon = expanded ? "−" : "+";
    const betCount = g.bets.length;
    const countLabel = betCount > 1 ? `<span class="history-session-count">${betCount}</span>` : "";
    const sessionLabel = g.session_date_utc === "—" ? "—" : `${g.session_date_utc} ${g.session_time_utc}`;
    const focused = agentSessionId && g.sessionId === agentSessionId ? " history-session-row-agent-focus" : "";
    return `<tr class="history-session-row${expanded ? " history-session-row-expanded" : ""}${focused}" data-session-id="${g.sessionId}"><td class="history-session-datetime">${sessionLabel}${countLabel}</td><td class="history-toggle-col"><span class="history-toggle-icon" aria-hidden="true">${icon}</span></td><td>${g.date_utc}</td><td>${g.time_utc}</td><td class="text-muted-app">—</td><td class="text-muted-app">—</td><td class="text-muted-app">—</td><td>$${g.size_usd.toFixed(2)}</td><td class="text-muted-app">—</td><td class="text-muted-app">—</td>${valCell(g.final_pnl_usd, "history-session-val")}${valCell(g.pnl_usd, "history-session-val")}</tr>`;
}


export function renderHistory(rows, { tbodyId = "historyTableBody", forceExpanded = false, agentSessionId = null } = {}) {
    const groups = groupHistoryRows(rows);
    const html = [];
    for (const g of groups) {
        const expanded = forceExpanded || expandedHistorySessions.has(g.sessionId);
        html.push(historySessionRow(g, expanded, agentSessionId));
        for (const r of g.bets) html.push(historyBetRow(r, !expanded));
    }
    $(tbodyId).innerHTML = html.join("");
}


/** History chiusa della sola session_id corrente (tab Candles). */
export function renderSessionHistory(rows, sessionId, agentSessionId = null) {
    const filtered = sessionId ? rows.filter((r) => r.session_id === sessionId) : [];
    renderHistory(filtered, { tbodyId: "sessionHistoryTableBody", forceExpanded: true, agentSessionId });
}


export function toggleHistorySession(sessionId) {
    if (expandedHistorySessions.has(sessionId)) expandedHistorySessions.delete(sessionId);
    else expandedHistorySessions.add(sessionId);
}


export function renderAccounts(state) {
    const accounts = state.accounts || [];
    const activeId = state.activeAccountId;
    const locked = !!state.session?.loaded || !!state.session?.account_switch_locked;
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
    $("newAccountBtn").disabled = locked;
    $("renameAccountBtn").disabled = !hasActive;
    $("editAccountBtn").disabled = !hasActive;
    $("exportCsvBtn").disabled = !hasActive;
    renderAccountSummary(state.activeAccount);
    renderBotPanel(state);
}


export function renderBotPanel(state) {
    const sw = $("botActiveSwitch");
    sw.disabled = false;
    sw.checked = !!state.botActive;
    $("botStatusLabel").textContent = state.botActive ? "READY" : "PAUSED";

    const activeIds = state.activeStrategyIds || [];
    const byId = Object.fromEntries((state.strategies || []).map((s) => [s.id, s]));
    const activeQueue = $("botActiveList");
    if (!activeIds.length) {
        activeQueue.innerHTML = `<span class="strategy-empty">No active strategies.</span>`;
    } else {
        activeQueue.innerHTML = activeIds.map((id) => {
            const s = byId[id] || { id, name: id };
            return `<span class="bot-active-label" data-id="${s.id}">
                <span class="bot-active-label-name" title="${escapeHtml(s.name)}">${escapeHtml(s.name)}</span>
                <span class="bot-active-label-sep" aria-hidden="true"></span>
                <button type="button" class="bot-active-label-x" data-unload="${s.id}" title="Remove from bot" aria-label="Remove ${escapeHtml(s.name)}"><i class="bi bi-x-lg" aria-hidden="true"></i></button>
            </span>`;
        }).join("");
    }

    const type = state.strategyType || "deterministic";
    const typeSelect = $("strategyTypeSelect");
    if (typeSelect.value !== type) typeSelect.value = type;
    const catalog = (state.strategies || []).filter((s) => s.type === type);
    const selectedId = state.selectedStrategyId;
    const catalogList = $("strategyCatalogList");
    if (!catalog.length) {
        catalogList.innerHTML = `<li class="strategy-empty">No ${escapeHtml(type)} strategies.</li>`;
    } else {
        catalogList.innerHTML = catalog.map((s) => {
            const sel = s.id === selectedId ? " selected" : "";
            const isActive = activeIds.includes(s.id);
            const desc = (s.description || "").trim();
            const tip = desc || "Double-click to edit";
            const descHtml = desc
                ? `<span class="desc">${escapeHtml(desc)}</span>`
                : "";
            return `<li class="strategy-catalog-item${sel}" data-id="${s.id}" title="${escapeHtml(tip)}">
                <div class="meta">
                    <div class="title-row">
                        <span class="name">${escapeHtml(s.name)}</span>
                        <span class="stype">${escapeHtml(s.type).toUpperCase()}</span>
                    </div>
                    ${descHtml}
                </div>
                <button type="button" class="btn-strat-add" data-action="load" data-id="${s.id}" title="Add to bot" aria-label="Add" ${isActive ? "disabled" : ""}><i class="bi bi-plus-lg" aria-hidden="true"></i></button>
            </li>`;
        }).join("");
    }
    const hasSel = !!selectedId && catalog.some((s) => s.id === selectedId);
    $("strategyEditBtn").disabled = !hasSel;
    $("strategyCloneBtn").disabled = !hasSel;
    $("strategyDeleteBtn").disabled = !hasSel;
}


/** Solo selezione UI: non ricostruire il catalogo (altrimenti il dblclick non parte). */
export function markStrategySelected(state, strategyId) {
    state.selectedStrategyId = strategyId;
    const catalogList = $("strategyCatalogList");
    catalogList.querySelectorAll(".strategy-catalog-item").forEach((el) => {
        el.classList.toggle("selected", el.dataset.id === strategyId);
    });
    const hasSel = !!strategyId && !!catalogList.querySelector(`.strategy-catalog-item[data-id="${strategyId}"]`);
    $("strategyEditBtn").disabled = !hasSel;
    $("strategyCloneBtn").disabled = !hasSel;
    $("strategyDeleteBtn").disabled = !hasSel;
}


export function renderAgentChat(messages, { thinking = false } = {}) {
    const log = $("agentChatLog");
    const parts = (messages || []).map((m) => {
        const role = m.role === "user" ? "user" : "assistant";
        return `<div class="agent-msg ${role}"><div class="agent-msg-role">${role}</div>`
            + `<div class="agent-msg-body">${renderAgentMarkdown(m.content || "")}</div></div>`;
    });
    if (thinking) {
        parts.push(
            `<div class="agent-msg assistant agent-thinking" id="agentThinkingBubble">`
            + `<div class="agent-msg-role">assistant</div>Thinking…</div>`
        );
    }
    log.innerHTML = parts.join("");
    log.scrollTop = log.scrollHeight;
}


export function renderAgentContext(state) {
    const acc = state.activeAccount;
    const focus = state.agentFocus || {};
    const isLive = !!focus.is_live;
    const sessionStratIds = isLive
        ? (state.activeStrategyIds || focus.strategy_ids || [])
        : (focus.strategy_ids || []);
    const loadedLabel = sessionStratIds.map((id) => {
        const s = state.strategies.find((x) => x.id === id);
        return s ? s.name : id;
    }).join(", ") || "—";
    const roundVal = focus.market_start_ts != null ? String(focus.market_start_ts) : "—";
    const secVal = isLive ? (focus.sec != null ? String(focus.sec) : "—") : "0";
    const sessions = state.executionSessions || [];
    const focusId = state.agentSessionId || "";
    const canUnload = !!state.session?.loaded;
    const unloadOpt = canUnload
        ? `<option value="__unload__">Unload session</option>`
        : `<option value="__unload__" disabled>Unload session</option>`;
    const opts = unloadOpt + sessions.map((s) => {
        const liveMark = s.session_id === state.session?.session_id ? " · live" : "";
        const when = formatSessionClock(s.market_start_ts);
        const label = `${s.session_id} · ${when} · ${s.n_events || 0} events${liveMark}`;
        const selected = s.session_id === focusId ? " selected" : "";
        return `<option value="${escapeHtml(s.session_id)}"${selected}>${escapeHtml(label)}</option>`;
    }).join("");
    const sessionControl =
        `<select class="form-select form-select-sm agent-session-select" id="agentSessionSelect">${opts}</select>`;
    const statsLine = formatSessionFocusStats(state);
    const parts = [
        cell("Account", acc ? acc.name : "—"),
        cell("Round", roundVal),
        cell("Sec", secVal),
        `<span class="agent-ctx-item agent-ctx-session"><strong>Session</strong>${sessionControl}</span>`,
        cell("Bot", state.botActive ? "ACTIVE" : "PAUSED"),
        `<span class="agent-ctx-item agent-ctx-loaded"><strong>Loaded strategies</strong>`
            + `<span title="${escapeHtml(loadedLabel)}">${escapeHtml(loadedLabel)}</span></span>`,
        cell("Session result", statsLine),
    ];
    $("agentContextBody").innerHTML = parts.join("");
}

function formatSessionFocusStats(state) {
    const sid = state.agentSessionId;
    if (!sid) return "—";
    const bets = (state.historyRows || []).filter((r) => r.session_id === sid);
    if (!bets.length) return "0 · PnL — · Size —";
    const pnl = sumField(bets, "final_pnl_usd");
    const pnlFallback = pnl == null ? sumField(bets, "pnl_usd") : pnl;
    const size = sessionCapitalSizeUsd(bets);
    const pnlStr = pnlFallback == null
        ? "—"
        : `${pnlFallback >= 0 ? "+" : ""}$${pnlFallback.toFixed(2)}`;
    return `${bets.length} · PnL ${pnlStr} · Size $${size.toFixed(2)}`;
}

function cell(label, value) {
    return `<span class="agent-ctx-item"><strong>${escapeHtml(label)}</strong>`
        + `<span title="${escapeHtml(value)}">${escapeHtml(value)}</span></span>`;
}


/** market_start_ts → dd-MM HH:mm (UTC). */
function formatSessionClock(mts) {
    if (mts == null || mts === "") return "—";
    const d = new Date(Number(mts) * 1000);
    const dd = String(d.getUTCDate()).padStart(2, "0");
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const mi = String(d.getUTCMinutes()).padStart(2, "0");
    return `${dd}-${mm} ${hh}:${mi}`;
}

export function renderAgentProposed(proposed, strategyId) {
    const wrap = $("agentProposedWrap");
    const btn = $("agentApplyRulesBtn");
    if (!proposed?.rules) {
        wrap.classList.add("d-none");
        btn.disabled = true;
        btn.dataset.strategyId = "";
        btn.dataset.rules = "";
        return;
    }
    wrap.classList.remove("d-none");
    $("agentProposedRules").textContent = proposed.rules;
    btn.disabled = !strategyId;
    btn.dataset.strategyId = strategyId || "";
    btn.dataset.rules = proposed.rules;
}


function renderAgentMarkdown(text) {
    // marked è globale (vendor); breaks=true → newline → <br>
    return marked.parse(String(text), { breaks: true, async: false });
}


function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
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
