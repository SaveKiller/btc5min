/** Lightweight Charts v5 — candele replay senza dati futuri. */

let chart = null;
let candleSeries = null;
let chartContainer = null;
let candleCount = 0;
let currentRoundCandleTime = null;
let chartViewFree = false;
let chartAutoscaleLockPending = false;
let autoscaleLockScheduled = false;
let layoutQueued = false;


function candleValid(c) {
    return c && [c.time, c.open, c.high, c.low, c.close].every((v) => Number.isFinite(v));
}


function enableFreeInteraction() {
    if (!chart) return;
    chart.applyOptions({
        handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
        handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: { time: true, price: true } },
    });
    chart.timeScale().applyOptions({ fixLeftEdge: false, fixRightEdge: false, rightOffset: 0, minBarSpacing: 2 });
}


function scheduleAutoscaleLock() {
    if (autoscaleLockScheduled) return;
    autoscaleLockScheduled = true;
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            autoscaleLockScheduled = false;
            chartAutoscaleLockPending = false;
            candleSeries?.priceScale().applyOptions({ autoScale: false });
        });
    });
}


function fitRoundStartViewport() {
    if (!chart || !candleCount || !chartContainer?.clientWidth || !chartContainer?.clientHeight) return false;
    const w = Math.max(120, chartContainer.clientWidth - 58);
    chart.timeScale().applyOptions({ barSpacing: Math.max(4, w / candleCount) });
    chart.timeScale().setVisibleLogicalRange({ from: 0, to: Math.max(1, candleCount) });
    candleSeries.priceScale().applyOptions({ autoScale: true });
    return true;
}


function applyChartLayout() {
    layoutQueued = false;
    if (!chart || !chartContainer) return;
    resizeChart();
    if (!candleCount || !chartContainer.clientWidth || !chartContainer.clientHeight) {
        queueChartLayout();
        return;
    }
    if (chartViewFree) {
        if (fitRoundStartViewport()) {
            chartViewFree = false;
            scheduleAutoscaleLock();
        }
        return;
    }
    if (chartAutoscaleLockPending) scheduleAutoscaleLock();
}


function queueChartLayout() {
    if (layoutQueued) return;
    layoutQueued = true;
    requestAnimationFrame(() => {
        requestAnimationFrame(() => applyChartLayout());
    });
}


export function initChart(container) {
    chartContainer = container;
    chart = LightweightCharts.createChart(container, {
        layout: { background: { color: "#111925" }, textColor: "#94a3b8" },
        grid: { vertLines: { color: "rgba(112,129,160,.09)" }, horzLines: { color: "rgba(112,129,160,.09)" } },
        rightPriceScale: { borderColor: "#526078" },
        timeScale: { borderColor: "#526078", timeVisible: true, secondsVisible: false },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        handleScroll: false, handleScale: false,
    });
    candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: "#22c55e", downColor: "#ef4444", borderVisible: false,
        wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    new ResizeObserver(() => queueChartLayout()).observe(container);
}


export function setCandles(previous, current, opts = {}) {
    const data = [...(previous || []).filter(candleValid)];
    if (current && candleValid(current)) data.push(current);
    data.sort((a, b) => a.time - b.time);
    candleCount = data.length;
    currentRoundCandleTime = current?.time ?? null;
    chartViewFree = !!opts.freeView;
    chartAutoscaleLockPending = !opts.freeView;
    candleSeries.priceScale().applyOptions({ autoScale: true });
    candleSeries.setData(data.map((c) => ({
        time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })));
    enableFreeInteraction();
    queueChartLayout();
}


export function updateCurrentCandle(candle) {
    if (!candle || !candleValid(candle)) return;
    if (!candleCount) {
        setCandles([], candle, { freeView: chartViewFree });
        return;
    }
    if (currentRoundCandleTime !== candle.time) {
        candleCount += 1;
        currentRoundCandleTime = candle.time;
    }
    candleSeries.update({
        time: candle.time, open: candle.open, high: candle.high, low: candle.low, close: candle.close,
    });
}


export function resizeChart() {
    if (!chart || !chartContainer) return;
    chart.applyOptions({ width: chartContainer.clientWidth, height: chartContainer.clientHeight });
}


export function relayoutChart() {
    queueChartLayout();
}
