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


const BAND_EDGE_PAD_PX = 12;
const BAND_END_PAD_PX = 26;


function timelineThumbPx() {
    const label = document.getElementById("timelineSecLabel");
    return Math.max(label?.offsetWidth || 0, 40);
}


function timelineThumbLeft(pct) {
    const tw = timelineThumbPx();
    return `calc(${pct * 100}% + ${(0.5 - pct) * tw}px)`;
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
        const endPad = inclusive ? BAND_END_PAD_PX : 0;
        band.style.left = `calc(${from.pct * 100}% + ${(0.5 - from.pct) * timelineThumbPx()}px - ${from.half + startPad}px)`;
        band.style.width = `calc(${spanPct * 100}% + ${(from.pct - until.pct) * timelineThumbPx()}px + ${from.half + endHalf + startPad + endPad}px)`;
    });
}


function applySecBandClass(el, sec) {
    el.classList.toggle("sec-green", sec <= 240 && sec > 180);
    el.classList.toggle("sec-azure", sec <= 180 && sec > 120);
    el.classList.toggle("sec-warn", sec <= 120 && sec > 60);
    el.classList.toggle("sec-critical", sec <= 60);
}


export function updateTimelineSecLabel(sec, progress) {
    const slider = $("timelineSlider");
    const label = $("timelineSecLabel");
    const wrap = slider.parentElement;
    label.textContent = String(sec);
    applySecBandClass(label, sec);
    applySecBandClass(slider, sec);
    const tw = Math.max(label.offsetWidth, 40);
    wrap.style.setProperty("--timeline-thumb-w", `${tw}px`);
    const min = Number(slider.min);
    const max = Number(slider.max);
    const pct = (progress - min) / (max - min);
    label.style.left = timelineThumbLeft(pct);
    if (wrap.dataset.thumbW !== String(tw)) {
        wrap.dataset.thumbW = String(tw);
        layoutReplayScale();
    }
}


export function renderStakeButtons() {
    const amounts = [1, 10, 50, 100];
    document.querySelectorAll(".stake[data-side]").forEach((wrap) => {
        wrap.innerHTML = amounts.map((n) => `<button class="btn btn-sm btn-outline-secondary stake-btn" type="button" data-amount="${n}">${n}</button>`).join("");
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
        // Durante scrub la posizione è solo del drag locale (vedi input su timelineSlider).
        if (!state.scrubbing) {
            $("timelineSlider").value = String(session.progress);
            updateTimelineSecLabel(session.sec, session.progress);
        }
        $("refPtb").textContent = Math.round(session.ptb_chainlink).toLocaleString("en-US");
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
    $("unloadRoundBtn").disabled = !state.session?.loaded;
    $("exportCsvBtn").disabled = !hasActive;
    renderAccountSummary(state.activeAccount);
    renderBotPanel(state);
}


export function renderBotPanel(state) {
    const sw = $("botActiveSwitch");
    sw.disabled = false;
    sw.checked = !!state.botActive;
    $("botStatusLabel").textContent = state.botActive ? "READY" : "PAUSED";
    $("botTabIcon").className = state.botActive
        ? "bi bi-cpu tab-icon bot-tab-icon is-active"
        : "bi bi-cpu tab-icon bot-tab-icon is-paused";
    $("botStatusIcon").className = state.botActive
        ? "bi bi-cpu bot-status-icon is-active"
        : "bi bi-cpu bot-status-icon is-paused";


    const activeIds = state.activeStrategyIds || [];
    const activeVer = Object.fromEntries(
        (state.activeStrategies || []).map((e) => [e.id, e.version]));
    const byId = Object.fromEntries((state.strategies || []).map((s) => [s.id, s]));
    const activeQueue = $("botActiveList");
    if (!activeIds.length) {
        activeQueue.innerHTML = `<span class="strategy-empty">No active strategies.</span>`;
    } else {
        activeQueue.innerHTML = activeIds.map((id) => {
            const s = byId[id] || { id, name: id };
            const ver = activeVer[id];
            const label = ver != null ? `${s.name} v${ver}` : s.name;
            return `<span class="bot-active-label" data-id="${s.id}">
                <span class="bot-active-label-name" title="${escapeHtml(label)}">${escapeHtml(label)}</span>
                <span class="bot-active-label-sep" aria-hidden="true"></span>
                <button type="button" class="bot-active-label-x" data-unload="${s.id}" title="Remove from bot" aria-label="Remove ${escapeHtml(label)}"><i class="bi bi-x-lg" aria-hidden="true"></i></button>
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
            const catalogVer = state.strategyCatalogVersions?.[s.id] ?? s.version ?? 1;
            const desc = (s.description || "").trim();
            const tip = desc || "Double-click to edit";
            const descHtml = desc
                ? `<span class="desc">${escapeHtml(desc)}</span>`
                : "";
            return `<li class="strategy-catalog-item${sel}" data-id="${s.id}" data-version="${catalogVer}" title="${escapeHtml(tip)}">
                <div class="meta">
                    <div class="title-row">
                        <span class="name-wrap">
                            <span class="name">${escapeHtml(s.name)}</span>
                            <span class="sver">V${catalogVer}</span>
                        </span>
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


export function renderAgentChat(messages, { thinking = false, thinkingText = "Thinking…" } = {}) {
    const log = $("agentChatLog");
    const parts = (messages || []).map((m) => {
        const role = m.role === "user" ? "user" : "assistant";
        return `<div class="agent-msg ${role}"><div class="agent-msg-role">${role}</div>`
            + `<div class="agent-msg-body">${renderAgentMarkdown(m.content || "")}</div></div>`;
    });
    if (thinking) {
        parts.push(
            `<div class="agent-msg assistant agent-thinking" id="agentThinkingBubble">`
            + `<div class="agent-msg-role">assistant</div>`
            + `<div class="agent-thinking-text">${thinkingText || "Thinking…"}</div></div>`
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
    const body = $("agentContextBody");
    const wasOpen = !!body.querySelector("#agentSessionMenu.show");
    const parts = [
        cell("Account", acc ? acc.name : "—"),
        cell("Round", roundVal),
        buildSessionPicker(state),
        cell("Bot", state.botActive ? "ACTIVE" : "PAUSED"),
        `<span class="agent-ctx-item agent-ctx-loaded"><strong>Loaded strategies</strong>`
            + `<span title="${escapeHtml(loadedLabel)}">${escapeHtml(loadedLabel)}</span></span>`,
        cell("Session result", formatSessionFocusStats(state)),
        buildSessionTrashCell(state),
    ];
    body.innerHTML = parts.join("");
    const btn = $("agentSessionSelectBtn");
    if (btn) {
        bootstrap.Dropdown.getOrCreateInstance(btn, {
            autoClose: true,
            popperConfig: { strategy: "fixed" },
        });
        if (wasOpen) bootstrap.Dropdown.getOrCreateInstance(btn).show();
    }
}


function buildSessionPicker(state) {
    const sessions = state.executionSessions || [];
    const focusId = state.agentSessionId || "";
    const canUnload = !!state.session?.loaded;
    const betCounts = betCountBySession(state.historyRows || []);
    const focused = sessions.find((s) => s.session_id === focusId);
    const btnInner = focused
        ? sessionRowInnerHtml(focused, state.session?.session_id, betCounts.get(focused.session_id) || 0)
        : "—";
    const btnChatCls = focused?.has_chat ? " session-has-chat" : "";
    const day = state.sessionPickerDay;
    const menuHtml = day
        ? sessionPickerSessionsHtml(sessions, day, focusId, state.session?.session_id, canUnload, betCounts)
        : sessionPickerDaysHtml(sessions, canUnload);
    return `<span class="agent-ctx-item agent-ctx-session"><strong>Session</strong>`
        + `<div class="dropdown agent-session-dropdown">`
        + `<button class="btn btn-sm agent-session-btn dropdown-toggle${btnChatCls}" type="button" id="agentSessionSelectBtn"`
        + ` data-bs-toggle="dropdown" aria-expanded="false">`
        + `<span class="agent-session-btn-label">${btnInner}</span></button>`
        + `<ul class="dropdown-menu session-picker-menu" id="agentSessionMenu">${menuHtml}</ul>`
        + `</div></span>`;
}


function sessionPickerUnloadLi(canUnload) {
    const cls = canUnload ? "" : " disabled";
    const dis = canUnload ? "" : " disabled";
    return `<li><button class="dropdown-item${cls}" type="button" data-session-unload="1"${dis}>Unload session</button></li>`;
}


function sessionPickerDaysHtml(sessions, canUnload) {
    const days = groupSessionsByCreatedDay(sessions);
    const total = sessions.length;
    const items = days.map((d) => (
        `<li><button class="dropdown-item session-day-btn" type="button" data-session-day="${d.day}">`
        + `${d.day}<span class="text-muted-app ms-1">(${d.count})</span>`
        + `<i class="bi bi-chevron-right float-end opacity-50"></i></button></li>`
    )).join("");
    return sessionPickerUnloadLi(canUnload)
        + `<li><hr class="dropdown-divider"></li>`
        + `<li><h6 class="dropdown-header">Sessions: ${total}</h6></li>`
        + items;
}


function sessionPickerSessionsHtml(sessions, day, focusId, liveId, canUnload, betCounts) {
    const list = sessions.filter((s) => sessionCreatedDayLocal(s.started_at_utc) === day);
    const items = list.map((s) => {
        const active = s.session_id === focusId ? " active" : "";
        const chatCls = s.has_chat ? " session-has-chat" : "";
        const nBets = betCounts.get(s.session_id) || 0;
        return `<li><button class="dropdown-item session-row-item${active}${chatCls}" type="button" data-session-id="${escapeHtml(s.session_id)}">`
            + sessionRowInnerHtml(s, liveId, nBets)
            + `</button></li>`;
    }).join("");
    return sessionPickerUnloadLi(canUnload)
        + `<li><button class="dropdown-item session-picker-back" type="button" data-session-back="1">`
        + `<i class="bi bi-chevron-left me-1"></i>Giorni</button></li>`
        + `<li><hr class="dropdown-divider"></li>`
        + `<li><h6 class="dropdown-header">${escapeHtml(day)} locale</h6></li>`
        + items;
}


/** Badge scommesse | id | HH:mm creazione locale | R DD-MM HH:mm replay UTC | live. */
function sessionRowInnerHtml(s, liveId, nBets) {
    const live = s.session_id === liveId ? "live" : "";
    return `<span class="session-events-badge">${String(nBets).padStart(2, " ")}</span>`
        + `<span class="session-row-sep">|</span>`
        + `<span class="session-row-fields">`
        + `<span class="session-row-id">${escapeHtml(s.session_id)}</span>`
        + `<span class="session-row-sep">|</span>`
        + `<span class="session-row-created">${escapeHtml(sessionCreatedHmLocal(s.started_at_utc))}</span>`
        + `<span class="session-row-sep">|</span>`
        + `<span class="session-row-replay">R ${escapeHtml(formatReplayClock(s.market_start_ts))}</span>`
        + `<span class="session-row-sep">|</span>`
        + `<span class="session-row-live">${live}</span>`
        + `</span>`;
}


function betCountBySession(rows) {
    const map = new Map();
    for (const r of rows) {
        const sid = r.session_id;
        if (!sid) continue;
        map.set(sid, (map.get(sid) || 0) + 1);
    }
    return map;
}


function groupSessionsByCreatedDay(sessions) {
    const map = new Map();
    for (const s of sessions) {
        const day = sessionCreatedDayLocal(s.started_at_utc);
        map.set(day, (map.get(day) || 0) + 1);
    }
    return [...map.entries()]
        .map(([day, count]) => ({ day, count }))
        .sort((a, b) => (a.day < b.day ? 1 : -1));
}


/** ISO started_at_utc → YYYY-MM-DD (orologio locale PC). Unica eccezione locale in UI. */
function sessionCreatedDayLocal(iso) {
    const d = new Date(iso);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}


/** ISO started_at_utc → HH:mm (orologio locale PC). */
function sessionCreatedHmLocal(iso) {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, "0");
    const mi = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mi}`;
}


/** market_start_ts → DD-MM HH:mm (UTC). */
function formatReplayClock(mts) {
    const d = new Date(Number(mts) * 1000);
    const dd = String(d.getUTCDate()).padStart(2, "0");
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const mi = String(d.getUTCMinutes()).padStart(2, "0");
    return `${dd}-${mm} ${hh}:${mi}`;
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


function buildSessionTrashCell(state) {
    const dis = state.agentSessionId ? "" : " disabled";
    return `<span class="agent-ctx-item agent-ctx-trash">`
        + `<button class="btn btn-sm btn-link stats-session-trash flex-shrink-0 p-0" id="agentDeleteSessionBtn" type="button"${dis} aria-label="Delete session">`
        + `<i class="bi bi-trash" aria-hidden="true"></i></button>`
        + `</span>`;
}


function cell(label, value) {
    return `<span class="agent-ctx-item"><strong>${escapeHtml(label)}</strong>`
        + `<span title="${escapeHtml(value)}">${escapeHtml(value)}</span></span>`;
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


function fmtPnl(n) {
    const v = Number(n);
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toFixed(2)}`;
}


export function renderStatsMode(_mode) {
    // Visibilità Backtest/Analyze gestita dai tab principali.
}


export function renderStatsDays(dayFrom, dayTo) {
    $("statsDayFromDisplay").textContent = formatStatsDayDisplay(dayFrom);
    $("statsDayToDisplay").textContent = formatStatsDayDisplay(dayTo);
}


function formatStatsDayDisplay(iso) {
    if (!iso) return "";
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
}


const STATS_MONTHS_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];
const STATS_DOW_IT = ["lu", "ma", "me", "gi", "ve", "sa", "do"];


function statsYmParts(ym) {
    const [y, m] = ym.split("-").map(Number);
    return { y, m };
}


/** Celle mese (lunedì-first): iso YYYY-MM-DD, day 1..31. */
function statsMonthCells(ym) {
    const { y, m } = statsYmParts(ym);
    const first = new Date(Date.UTC(y, m - 1, 1));
    // getUTCDay: 0=dom … 6=sab → offset lunedì-first
    const startPad = (first.getUTCDay() + 6) % 7;
    const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
    const cells = [];
    for (let i = 0; i < startPad; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
        const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        cells.push({ iso, day: d, inMonth: true });
    }
    while (cells.length % 7) cells.push(null);
    return cells;
}


/**
 * Calendario START/END: giorni con dati evidenziati; altrimenti disabled.
 * boundMin/boundMax: vincolo reciproco START≤END.
 */
export function renderStatsDayCalendar(menuEl, {
    role, selected, boundMin, boundMax, validDays, viewYm,
}) {
    const { y, m } = statsYmParts(viewYm);
    const title = `${STATS_MONTHS_IT[m - 1]} ${y}`;
    const cells = statsMonthCells(viewYm);
    const dow = STATS_DOW_IT.map((d) => `<span>${d}</span>`).join("");
    const grid = cells.map((c) => {
        if (!c) return `<span></span>`;
        const available = validDays.has(c.iso);
        const inBound = (!boundMin || c.iso >= boundMin) && (!boundMax || c.iso <= boundMax);
        const enabled = available && inBound;
        const cls = [
            "stats-cal-day",
            c.iso === selected ? "is-selected" : "",
            enabled ? "is-available" : "is-muted",
        ].filter(Boolean).join(" ");
        const dis = enabled ? "" : " disabled";
        return `<button type="button" class="${cls}" data-day="${c.iso}"${dis}>${c.day}</button>`;
    }).join("");
    menuEl.dataset.viewYm = viewYm;
    menuEl.dataset.role = role;
    menuEl.innerHTML = `
      <div class="stats-cal-head">
        <button type="button" data-cal-nav="-1" aria-label="Mese precedente">‹</button>
        <span>${title}</span>
        <button type="button" data-cal-nav="1" aria-label="Mese successivo">›</button>
      </div>
      <div class="stats-cal-dow">${dow}</div>
      <div class="stats-cal-grid">${grid}</div>`;
}


function formatStatsExecDisplay(isoUtc) {
    if (!isoUtc) return "";
    return isoUtc.slice(0, 16).replace("T", " ");
}


export function renderStatsStrategySelect(strategies, selectedId, selectedVersion, jobRunning) {
    const btn = $("statsStrategyBtn");
    const menu = $("statsStrategyMenu");
    const list = strategies || [];
    const selected = selectedId && list.find((s) => s.id === selectedId);
    btn.textContent = selected ? selected.name : "Strategy";
    btn.classList.toggle("is-placeholder", !selected);
    btn.disabled = !!jobRunning;
    menu.innerHTML = `<li><button type="button" class="dropdown-item stats-bs-select-item${!selected ? " active" : ""}" data-value="">Strategy</button></li>`
        + list.map((s) => {
            const act = s.id === selectedId ? " active" : "";
            return `<li><button type="button" class="dropdown-item stats-bs-select-item${act}" data-value="${escapeHtml(s.id)}">${escapeHtml(s.name)}</button></li>`;
        }).join("");
    renderStatsStrategyVersionSelect(list, selected ? selected.id : null, selectedVersion, jobRunning);
    $("statsBacktestRunBtn").disabled = !!jobRunning || !selected;
}


export function renderStatsStrategyVersionSelect(strategies, selectedId, selectedVersion, jobRunning) {
    const btn = $("statsStrategyVersionBtn");
    const menu = $("statsStrategyVersionMenu");
    const s = (strategies || []).find((x) => x.id === selectedId);
    if (!s) {
        btn.textContent = "V —";
        btn.disabled = true;
        menu.innerHTML = "";
        return;
    }
    const versions = [...(s.versions || [{ version: s.version || 1 }])]
        .sort((a, b) => b.version - a.version);
    const tip = s.version || 1;
    const pick = selectedVersion != null && versions.some((v) => v.version === selectedVersion)
        ? selectedVersion : tip;
    btn.textContent = `V ${pick}`;
    btn.disabled = !!jobRunning;
    menu.innerHTML = versions.map((v) => {
        const act = v.version === pick ? " active" : "";
        return `<li><button type="button" class="dropdown-item stats-bs-select-item${act}" data-value="${v.version}">V ${v.version}</button></li>`;
    }).join("");
}


function fitSelectToLabels(btn, labels) {
    const cs = getComputedStyle(btn);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    let max = 0;
    for (const t of labels) max = Math.max(max, ctx.measureText(t).width);
    const pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    // freccia del form-select + bordo
    btn.style.width = `${Math.ceil(max + pad + 28)}px`;
}


const STATS_MONTHS_EN = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
];


function statsSimMonthYm(sim) {
    return (sim.exec_at || sim.created_at_utc || "").slice(0, 7);
}


function statsSimMonthLabel(ym) {
    const [y, m] = ym.split("-");
    return `${STATS_MONTHS_EN[Number(m) - 1]} ${y.slice(2)}`;
}


export function statsSimMonthList(simulations) {
    const set = new Set();
    for (const s of simulations) {
        const ym = statsSimMonthYm(s);
        if (ym.length === 7) set.add(ym);
    }
    return [...set].sort().reverse();
}


function filterStatsSimulations(simulations, monthYm, search) {
    const q = search.trim().toLowerCase();
    return simulations.filter((s) => {
        if (monthYm && statsSimMonthYm(s) !== monthYm) return false;
        if (!q) return true;
        const hay = [
            s.label, s.name_ver, s.exec_at, s.range_label, String(s.n_rounds ?? ""),
            s.strategy_name, String(s.strategy_version ?? ""),
        ].join(" ").toLowerCase();
        return hay.includes(q);
    });
}


export function renderStatsSimPeriodSelect(months, selectedYm) {
    const btn = $("statsSimPeriodBtn");
    const menu = $("statsSimPeriodMenu");
    const selected = selectedYm && months.includes(selectedYm) ? selectedYm : (months[0] || null);
    btn.textContent = selected ? statsSimMonthLabel(selected) : "—";
    btn.classList.toggle("is-placeholder", !selected);
    fitSelectToLabels(btn, months.length
        ? months.map(statsSimMonthLabel)
        : ["—"]);
    btn.parentElement.style.width = btn.style.width;
    if (!months.length) {
        menu.innerHTML = `<li><span class="dropdown-item-text text-muted-app tiny px-3">—</span></li>`;
        return selected;
    }
    menu.innerHTML = months.map((ym) => {
        const act = ym === selected ? " active" : "";
        return `<li><button type="button" class="dropdown-item stats-bs-select-item${act}" data-value="${escapeHtml(ym)}">${escapeHtml(statsSimMonthLabel(ym))}</button></li>`;
    }).join("");
    return selected;
}


export function renderStatsSimulationSelect(simulations, selectedId, monthYm, search) {
    const btn = $("statsSimulationBtn");
    const menu = $("statsSimulationMenu");
    const block = $("statsSimBlock");
    const list = filterStatsSimulations(simulations, monthYm, search);
    const selected = selectedId && list.find((s) => s.id === selectedId);
    const emptyLabel = `${list.length} Simulations found`;
    btn.textContent = selected ? (selected.label || selected.id) : emptyLabel;
    btn.classList.toggle("is-placeholder", !selected);
    const widthLabels = [emptyLabel, ...simulations.map((s) => s.label || s.id || "")];
    fitSelectToLabels(btn, widthLabels);
    block.style.width = btn.style.width;
    btn.style.width = "100%";
    $("statsSimulationDeleteBtn").disabled = !selected;
    if (!list.length) {
        menu.innerHTML = `<li><span class="dropdown-item-text text-muted-app tiny px-3">${emptyLabel}</span></li>`;
        return;
    }
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const cs = getComputedStyle(btn);
    ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const w = [0, 0, 0, 0];
    for (const s of list) {
        w[0] = Math.max(w[0], ctx.measureText(s.name_ver).width);
        w[1] = Math.max(w[1], ctx.measureText(s.exec_at).width);
        w[2] = Math.max(w[2], ctx.measureText(s.range_label).width);
        w[3] = Math.max(w[3], ctx.measureText(String(s.n_rounds)).width);
    }
    menu.style.setProperty("--sim-c1", `${Math.ceil(w[0])}px`);
    menu.style.setProperty("--sim-c2", `${Math.ceil(w[1])}px`);
    menu.style.setProperty("--sim-c3", `${Math.ceil(w[2])}px`);
    menu.style.setProperty("--sim-c4", `${Math.ceil(w[3])}px`);
    menu.innerHTML = `<li><button type="button" class="dropdown-item stats-bs-select-item${!selected ? " active" : ""}" data-value="">${emptyLabel}</button></li>`
        + list.map((s) => {
            const act = s.id === selectedId ? " active" : "";
            return `<li><button type="button" class="dropdown-item stats-bs-select-item stats-sim-row${act}" data-value="${escapeHtml(s.id)}">`
                + `<span class="stats-sim-col-name">${escapeHtml(s.name_ver)}</span>`
                + `<span class="stats-sim-col-exec">${escapeHtml(s.exec_at)}</span>`
                + `<span class="stats-sim-col-range">${escapeHtml(s.range_label)}</span>`
                + `<span class="stats-sim-col-rounds">${Number(s.n_rounds)}</span>`
                + `</button></li>`;
        }).join("");
}


export function renderStatsAnalyzeSimSelect(simulations, selectedIds) {
    const btn = $("statsAnalyzeSimBtn");
    const menu = $("statsAnalyzeSimMenu");
    const placeholder = "— seleziona simulation —";
    const list = (simulations || []).filter((s) => s.has_orders);
    const ids = selectedIds || [];
    const selected = new Set(ids);
    let label = placeholder;
    if (ids.length === 1) {
        const one = list.find((s) => s.id === ids[0]);
        label = one ? (one.label || one.id) : ids[0];
    } else if (ids.length > 1) {
        label = `${ids.length} simulation selezionate`;
    }
    btn.textContent = label;
    const longest = list.reduce((n, s) => Math.max(n, (s.label || s.id || "").length), placeholder.length);
    btn.style.width = `${Math.min(longest + 4, 64)}ch`;
    if (!list.length) {
        menu.innerHTML = `<li><span class="dropdown-item-text text-muted-app tiny px-3">— nessuna simulation —</span></li>`;
        return;
    }
    menu.innerHTML = list.map((s) => {
        const id = escapeHtml(s.id);
        const checked = selected.has(s.id) ? " checked" : "";
        return `<li><label class="dropdown-item stats-analyze-sim-item">`
            + `<input class="form-check-input" type="checkbox" data-sim-id="${id}"${checked}>`
            + `<span>${escapeHtml(s.label || s.id)}</span></label></li>`;
    }).join("");
}


export function renderStatsJobUi(state) {
    const running = !!state.statsJobRunning;
    const prog = state.statsProgress;
    const kind = prog?.kind;
    const done = prog ? Number(prog.done) || 0 : 0;
    const total = prog ? Number(prog.total) || 0 : 0;
    const pct = total ? Math.min(100, Math.round(100 * done / total)) : 0;
    const label = prog ? `${done} / ${total}` : "—";
    const showBt = running && kind === "backtest";
    const showAn = running && kind === "analyze";
    $("statsProgressBar").style.width = `${showBt ? pct : 0}%`;
    $("statsProgressLabel").textContent = showBt ? label : "—";
    $("statsAnalyzeProgressBar").style.width = `${showAn ? pct : 0}%`;
    $("statsAnalyzeProgressLabel").textContent = showAn ? label : "—";
    const hasStrategy = !!state.statsStrategyId;
    $("statsBacktestRunBtn").disabled = running || !hasStrategy;
    $("statsStrategyBtn").disabled = running;
    $("statsStrategyVersionBtn").disabled = running || !hasStrategy;
    $("statsJobCancelBtn").disabled = !running;
}


function pad2(n) {
    return String(n).padStart(2, "0");
}


function emptyStatsAgg() {
    return {
        rounds: 0, traded: 0, pos: 0, neg: 0, flat: 0,
        pnl_sum: 0.0, pos_sum: 0.0, neg_sum: 0.0,
        pnl_avg_pos: null, pnl_avg_neg: null,
    };
}


function accumulateStatsAgg(b, r) {
    if (!r.ok) return;
    b.rounds += 1;
    if (r.traded) b.traded += 1;
    const pnl = Number(r.pnl_usd);
    b.pnl_sum += pnl;
    if (pnl > 0) { b.pos += 1; b.pos_sum += pnl; }
    else if (pnl < 0) { b.neg += 1; b.neg_sum += pnl; }
    else b.flat += 1;
}


function finalizeStatsAgg(b) {
    b.pnl_avg_pos = b.pos ? b.pos_sum / b.pos : null;
    b.pnl_avg_neg = b.neg ? b.neg_sum / b.neg : null;
    return b;
}


function totalStatsAgg(rows) {
    const t = emptyStatsAgg();
    for (const r of rows) {
        for (const k of ["rounds", "traded", "pos", "neg", "flat"]) t[k] += r[k];
        t.pnl_sum += r.pnl_sum;
        t.pos_sum += r.pos_sum;
        t.neg_sum += r.neg_sum;
    }
    return finalizeStatsAgg(t);
}


function utcRoundParts(ts) {
    const d = new Date(Number(ts) * 1000);
    const hour = d.getUTCHours();
    const minute = d.getUTCMinutes();
    return {
        hour, minute, slot: Math.floor(minute / 5),
        day: `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`,
    };
}


function slotRangeLabel(hour, slot) {
    const m0 = slot * 5;
    const endMinute = m0 + 5;
    const endH = endMinute === 60 ? (hour + 1) % 24 : hour;
    const endM = endMinute === 60 ? 0 : endMinute;
    return `${pad2(hour)}:${pad2(m0)}–${pad2(endH)}:${pad2(endM)}`;
}


function aggStatsHours(rounds) {
    const buckets = Array.from({ length: 24 }, (_, h) => ({
        key: String(h), label: `${pad2(h)}:00`, market: UTC_HOUR_MARKETS[h], ...emptyStatsAgg(),
    }));
    for (const r of rounds) {
        if (!r.ok) continue;
        const h = r.hour_utc != null ? Number(r.hour_utc) : utcRoundParts(r.market_start_ts).hour;
        accumulateStatsAgg(buckets[h], r);
    }
    const rows = buckets.map(finalizeStatsAgg);
    return { rows, total: totalStatsAgg(rows) };
}


function aggStatsSlots(rounds, hour) {
    const buckets = Array.from({ length: 12 }, (_, s) => ({
        key: String(s), label: slotRangeLabel(hour, s), market: UTC_HOUR_MARKETS[hour], ...emptyStatsAgg(),
    }));
    for (const r of rounds) {
        if (!r.ok) continue;
        const p = utcRoundParts(r.market_start_ts);
        if (p.hour !== hour) continue;
        accumulateStatsAgg(buckets[p.slot], r);
    }
    const rows = buckets.map(finalizeStatsAgg);
    return { rows, total: totalStatsAgg(rows) };
}


function aggStatsDays(rounds, hour, slot) {
    const byDay = new Map();
    const range = slotRangeLabel(hour, slot);
    for (const r of rounds) {
        if (!r.ok) continue;
        const p = utcRoundParts(r.market_start_ts);
        if (p.hour !== hour || p.slot !== slot) continue;
        if (!byDay.has(p.day)) {
            byDay.set(p.day, {
                key: p.day, label: `${p.day} · ${range}`, market: UTC_HOUR_MARKETS[hour],
                market_start_ts: r.market_start_ts, ...emptyStatsAgg(),
            });
        }
        accumulateStatsAgg(byDay.get(p.day), r);
    }
    const rows = [...byDay.values()].sort((a, b) => a.key.localeCompare(b.key)).map(finalizeStatsAgg);
    return { rows, total: totalStatsAgg(rows) };
}


function statsPnlTd(n) {
    if (n == null) return `<td class="text-end"></td>`;
    const v = Number(n);
    const cls = v > 0 ? "stats-sum-pos" : v < 0 ? "stats-sum-neg" : "";
    return `<td class="text-end${cls ? ` ${cls}` : ""}">${fmtPnl(v)}</td>`;
}


function statsAggRowHtml(row, { drill = false, roundTs = null } = {}) {
    const clickable = drill || roundTs != null;
    const cls = clickable ? "stats-row-drill" : "";
    let data = "";
    if (roundTs != null) data = ` data-round-ts="${Number(roundTs)}"`;
    else if (drill) data = ` data-drill-key="${escapeHtml(row.key)}"`;
    return `<tr class="${cls}"${data}>
        <td>${escapeHtml(row.label)}</td>
        <td>${escapeHtml(row.market)}</td>
        <td class="text-end">${row.rounds}</td>
        <td class="text-end stats-sum-pos">${row.pos}</td>
        <td class="text-end stats-sum-neg">${row.neg}</td>
        <td class="text-end">${row.flat}</td>
        ${statsPnlTd(row.pnl_sum)}
        ${statsPnlTd(row.pos ? row.pos_sum : null)}
        ${statsPnlTd(row.neg ? row.neg_sum : null)}
        ${statsPnlTd(row.pnl_avg_pos)}
        ${statsPnlTd(row.pnl_avg_neg)}
    </tr>`;
}


function statsTotalRowHtml(total) {
    return `<tr class="stats-backtest-table-total">
        <td colspan="2">TOTAL</td>
        <td class="text-end">${total.rounds}</td>
        <td class="text-end stats-sum-pos">${total.pos}</td>
        <td class="text-end stats-sum-neg">${total.neg}</td>
        <td class="text-end">${total.flat}</td>
        ${statsPnlTd(total.pnl_sum)}
        ${statsPnlTd(total.pos ? total.pos_sum : null)}
        ${statsPnlTd(total.neg ? total.neg_sum : null)}
        ${statsPnlTd(total.pnl_avg_pos)}
        ${statsPnlTd(total.pnl_avg_neg)}
    </tr>`;
}


function renderStatsResultsBreadcrumb(drill) {
    const el = $("statsResultsBreadcrumb");
    if (!el) return;
    const root = `<button type="button" data-crumb="hours">Risultati 24 ore UTC</button>`;
    if (!drill || drill.level === "hours") {
        el.innerHTML = `<span class="crumb-current">Risultati 24 ore UTC</span>`;
        return;
    }
    const hourLab = `${pad2(drill.hour)}:00`;
    if (drill.level === "slots") {
        el.innerHTML = `${root}<span class="crumb-sep">›</span><span class="crumb-current">${hourLab}</span>`;
        return;
    }
    const slotLab = slotRangeLabel(drill.hour, drill.slot);
    el.innerHTML = `${root}<span class="crumb-sep">›</span>`
        + `<button type="button" data-crumb="slots">${hourLab}</button>`
        + `<span class="crumb-sep">›</span><span class="crumb-current">${slotLab}</span>`;
}


function statsPnlClassGe0(n) {
    return Number(n) < 0 ? "stats-sum-neg" : "stats-sum-pos";
}


function fmtUsdInt(n) {
    return `${Math.round(Number(n))}$`;
}


function pctInt(part, total) {
    return total ? Math.round((100 * part) / total) : 0;
}


/** Aggregati da rounds ok: conteggi, somme pnl pos/neg, giorni unici. */
function computeStatsSessionDetail(rounds) {
    let n = 0, pos = 0, neg = 0, flat = 0;
    let pnl = 0, posSum = 0, negSum = 0;
    const days = new Set();
    for (const r of rounds) {
        if (!r.ok) continue;
        n += 1;
        const p = Number(r.pnl_usd);
        pnl += p;
        days.add(utcRoundParts(r.market_start_ts).day);
        if (p > 0) { pos += 1; posSum += p; }
        else if (p < 0) { neg += 1; negSum += p; }
        else flat += 1;
    }
    return {
        rounds: n, pos, neg, flat, n_days: days.size,
        pnl_total: pnl, pos_sum: posSum, neg_sum: negSum,
        pos_mean: pos ? posSum / pos : null,
        neg_mean: neg ? negSum / neg : null,
    };
}


function renderStatsSessionDetailHtml(d) {
    const n = d.rounds;
    const posPct = pctInt(d.pos, n);
    const negPct = pctInt(d.neg, n);
    const flatPct = pctInt(d.flat, n);
    const line1 = `ROUNDS: <span class="stats-sum-white">${n}</span>`
        + ` = <span class="stats-sum-pos">${d.pos}</span>`
        + ` + <span class="stats-sum-neg">${d.neg}</span>`
        + ` + <span class="stats-sum-flat">${d.flat}</span>`
        + ` = <span class="stats-sum-pos">${posPct}%</span>`
        + ` + <span class="stats-sum-neg">${negPct}%</span>`
        + ` + <span class="stats-sum-flat">${flatPct}%</span>`;
    const line2 = `TOTAL: <span class="${statsPnlClassGe0(d.pnl_total)}">${fmtUsdInt(d.pnl_total)}</span>`
        + ` = <span class="stats-sum-pos">${fmtUsdInt(d.pos_sum)}</span>`
        + ` - <span class="stats-sum-neg">${fmtUsdInt(Math.abs(d.neg_sum))}</span>`;
    const posMean = d.pos_mean == null ? "—" : `<span class="stats-sum-pos">${fmtUsdInt(d.pos_mean)}</span>`;
    const negMean = d.neg_mean == null ? "—" : `<span class="stats-sum-neg">${fmtUsdInt(d.neg_mean)}</span>`;
    const line3 = `MEAN: POS: ${posMean} , NEG: ${negMean}`;
    return `${line1}<br>${line2}<br>${line3}`;
}


export function renderStatsBacktest(state) {
    const summary = state?.statsSummary ?? null;
    const sumEl = $("statsSummaryLabel");
    const detailEl = $("statsSummaryDetail");
    const detailDiv = $("statsSummaryDetailDivider");
    const rounds = state?.statsRounds;
    if (summary) {
        const exec = formatStatsExecDisplay(summary.created_at_utc);
        const detail = rounds?.length ? computeStatsSessionDetail(rounds) : null;
        sumEl.innerHTML = (exec ? `RUN: <span class="stats-sum-white">${escapeHtml(exec)}</span><br>` : "")
            + `${escapeHtml(summary.day_from)}→${escapeHtml(summary.day_to)}`
            + (detail ? `<br>TOTAL DAYS: <span class="stats-sum-white">${detail.n_days}</span>` : "");
        if (detail) {
            detailEl.innerHTML = renderStatsSessionDetailHtml(detail);
            detailDiv.classList.remove("d-none");
        } else {
            detailEl.innerHTML = "";
            detailDiv.classList.add("d-none");
        }
    } else {
        sumEl.innerHTML = "";
        detailEl.innerHTML = "";
        detailDiv.classList.add("d-none");
    }

    const body = $("statsBacktestTableBody");
    const drill = state?.statsDrill || { level: "hours", hour: null, slot: null };
    renderStatsResultsBreadcrumb(rounds ? drill : null);

    if (!rounds?.length && !state?.statsTable?.hours) {
        body.innerHTML = "";
        $("statsColLabel").textContent = "Hour";
        return;
    }

    let view;
    let colLabel = "Hour";
    let rowMode = "plain"; // plain | drill | round
    if (rounds?.length) {
        if (drill.level === "slots") {
            view = aggStatsSlots(rounds, drill.hour);
            colLabel = "Slot";
            rowMode = "drill";
        } else if (drill.level === "days") {
            view = aggStatsDays(rounds, drill.hour, drill.slot);
            colLabel = "Day";
            rowMode = "round";
        } else {
            view = aggStatsHours(rounds);
            colLabel = "Hour";
            rowMode = "drill";
        }
    } else {
        // Fallback sessione senza rounds in memoria: solo L1 da table precomputata.
        view = {
            rows: state.statsTable.hours.map((h, i) => ({
                key: String(i), label: h.hour, market: h.market,
                rounds: h.rounds, traded: h.traded, pos: h.pos, neg: h.neg, flat: h.flat,
                pnl_sum: h.pnl_sum, pos_sum: h.pos_sum, neg_sum: h.neg_sum,
                pnl_avg_pos: h.pnl_avg_pos, pnl_avg_neg: h.pnl_avg_neg,
            })),
            total: state.statsTable.total,
        };
        rowMode = "plain";
    }

    $("statsColLabel").textContent = colLabel;
    const rows = view.rows.map((r) => {
        if (rowMode === "round") return statsAggRowHtml(r, { roundTs: r.market_start_ts });
        if (rowMode === "drill") return statsAggRowHtml(r, { drill: true });
        return statsAggRowHtml(r);
    });
    rows.push(statsTotalRowHtml(view.total));
    body.innerHTML = rows.join("");
}


export function renderStatsAnalyze(state) {
    renderStatsChat(state.statsChatMessages, { thinking: state.statsChatBusy });
}


export function renderStatsChat(messages, { thinking = false } = {}) {
    const log = $("statsChatLog");
    const parts = (messages || []).map((m) => {
        const role = m.role === "user" ? "user" : "assistant";
        return `<div class="agent-msg ${role}"><div class="agent-msg-role">${role}</div>`
            + `<div class="agent-msg-body">${renderAgentMarkdown(m.content || "")}</div></div>`;
    });
    if (thinking) {
        parts.push(
            `<div class="agent-msg assistant agent-thinking">`
            + `<div class="agent-msg-role">assistant</div>Thinking…</div>`
        );
    }
    log.innerHTML = parts.join("");
    log.scrollTop = log.scrollHeight;
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
