/** Lightweight Charts v5 — candele replay senza dati futuri. */

let chart = null;
let candleSeries = null;
let chartContainer = null;
let candleCount = 0;
let currentRoundCandleTime = null;


function enableFreeInteraction() {
    if (!chart) return;
    chart.applyOptions({
        handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
        handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: { time: true, price: true } },
    });
    chart.timeScale().applyOptions({ fixLeftEdge: false, fixRightEdge: false, rightOffset: 0, minBarSpacing: 2 });
}


function fitRoundStartViewport() {
    if (!chart || !candleCount) return;
    const w = Math.max(120, chartContainer.clientWidth - 58);
    chart.timeScale().applyOptions({ barSpacing: Math.max(4, w / candleCount) });
    chart.timeScale().setVisibleLogicalRange({ from: 0, to: candleCount });
    candleSeries.priceScale().applyOptions({ autoScale: false });
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
    new ResizeObserver(() => resizeChart()).observe(container);
}


export function setCandles(previous, current, opts = {}) {
    const data = [...previous];
    if (current) data.push(current);
    data.sort((a, b) => a.time - b.time);
    candleCount = data.length;
    currentRoundCandleTime = current?.time ?? null;
    candleSeries.priceScale().applyOptions({ autoScale: true });
    candleSeries.setData(data.map((c) => ({
        time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })));
    enableFreeInteraction();
    if (opts.freeView) fitRoundStartViewport();
    else candleSeries.priceScale().applyOptions({ autoScale: false });
}


export function updateCurrentCandle(candle) {
    if (!candle) return;
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
    resizeChart();
}
