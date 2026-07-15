/** Lightweight Charts v5 — candele replay senza dati futuri. */

let chart = null;
let candleSeries = null;


export function initChart(container) {
    chart = LightweightCharts.createChart(container, {
        layout: { background: { color: "#111925" }, textColor: "#94a3b8" },
        grid: { vertLines: { color: "rgba(112,129,160,.09)" }, horzLines: { color: "rgba(112,129,160,.09)" } },
        rightPriceScale: { borderColor: "#526078" },
        timeScale: { borderColor: "#526078", timeVisible: true, secondsVisible: false },
    });
    candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: "#22c55e", downColor: "#ef4444", borderVisible: false,
        wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth, height: container.clientHeight })).observe(container);
}


export function setCandles(previous, current) {
    const data = [...previous];
    if (current) data.push(current);
    data.sort((a, b) => a.time - b.time);
    candleSeries.setData(data.map((c) => ({
        time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })));
}


export function updateCurrentCandle(candle) {
    if (!candle) return;
    candleSeries.update({
        time: candle.time, open: candle.open, high: candle.high, low: candle.low, close: candle.close,
    });
}
