/* OpenTrader — chart UI for visual signal verification.
   Pure ES6, lightweight-charts v4. The backtest endpoint is the only data source.

   v4 has ONE pane, so the RSI occupies a pinned band on the left price scale
   instead of a true second pane. Money values from the API are strings and are
   rendered verbatim; only chart geometry is numeric.
*/

"use strict";

/* ---------------------------------- utilities ---------------------------------- */

function $(id) { return document.getElementById(id); }

const $log = (...args) => {
  if (console && console.debug) console.debug("[opentrader]", ...args);
};

const SHROUD_MS = 90;        // idle time before the shroud repositions after pan/zoom
const TRADE_PAD = 24;        // bars of context around a framed trade
const DEFAULT_INTERVAL = "1d";

const COLORS = { trace: "#E8A33D" };

/* ---------------------------------- dom handles ---------------------------------- */

const el = {
  controls: $("controls"),
  strategy: $("strategy"),
  interval: $("interval"),
  bars: $("bars"),
  run: $("run"),
  status: $("status"),
  error: $("error"),

  stage: $("stage"),
  chartEl: $("chart"),

  specSymbol: $("spec-symbol"),
  specEntry: $("spec-entry"),
  specStop: $("spec-stop"),
  specRR: $("spec-rr"),
  specRange: $("spec-range"),

  sumClosed: $("sum-closed"),
  sumWins: $("sum-wins"),
  sumLosses: $("sum-losses"),
  sumNet: $("sum-net"),
  sumOpen: $("sum-open"),

  warmSkipped: $("warm-skipped"),
  warmArmed: $("warm-armed"),

  headSymbol: $("head-symbol"),
  headInterval: $("head-interval"),
  headBars: $("head-bars"),

  chartbox: $("chartbox"),
  shroud: $("shroud"),
  armedLine: $("armed-line"),
  armedLabel: $("armed-label"),
  armedBar: $("armed-bar"),
  layer: $("layer"),
  paneRule: $("pane-rule"),
  paneTag: $("pane-tag"),

  logNote: $("log-note"),
  tbody: $("trade-rows"),
};

/* ---------------------------------- state ---------------------------------- */

const state = {
  intervals: [],
  result: null,
  chart: null,
  main: null,            // candlestick series (kept across runs)
  indicatorLines: [],    // non-pane indicator series (rebuilt per run)
  rsiSeries: null,       // pane indicator series, or null when none
  priceLines: [],        // active bracket lines
  markers: [],           // mirror of the marker set (v4 has no read-back)
  selectedRow: null,
  shroudTimer: null,
};

/* ---------------------------------- fetch helpers ---------------------------------- */

async function getJSON(url) {
  let res;
  try {
    const opts = { method: "GET" };
    if (typeof AbortSignal !== "undefined" && AbortSignal.timeout) {
      opts.signal = AbortSignal.timeout(120000);
    }
    res = await fetch(url, opts);
  } catch (err) {
    throw new Error("cannot reach the server: " + (err && err.message));
  }
  let data = null;
  try {
    data = await res.json();
  } catch { /* non-JSON body; fall through to the status-line message */ }
  if (!res.ok) throw new Error(extractDetail(data, res));
  return data;
}

function extractDetail(data, res) {
  if (data && typeof data === "object") {
    if (typeof data.detail === "string") return data.detail;
    // FastAPI 422 validation errors are a list of {loc, msg}.
    if (Array.isArray(data.detail) && data.detail.length) {
      return data.detail.map((d) => d.msg || String(d)).join("; ");
    }
  }
  return "HTTP " + res.status + (res.statusText ? " " + res.statusText : "");
}

function backtestUrl(strategy, interval, bars) {
  const url = new URL("/api/backtest", document.baseURI);
  url.searchParams.set("strategy", strategy);
  url.searchParams.set("interval", interval);
  url.searchParams.set("bars", String(bars));
  return url.toString();
}

/* ---------------------------------- loading / error ---------------------------------- */

function setBusy(busy, message) {
  el.stage.setAttribute("aria-busy", busy ? "true" : "false");
  el.run.setAttribute("aria-disabled", busy ? "true" : "false");
  el.run.textContent = busy ? "Running" : "Run backtest";
  el.status.textContent = message || "";
  if (busy) el.status.setAttribute("data-busy", "1");
  else el.status.removeAttribute("data-busy");
}

function setError(message) {
  if (!message) {
    el.error.hidden = true;
    el.error.textContent = "";
    return;
  }
  el.error.textContent = message;
  el.error.hidden = false;
}

/* ---------------------------------- time (payload stamps are UTC) ---------------------------------- */

function pad(n) { return String(n).padStart(2, "0"); }

/* Money arrives as an exact decimal string -- the server deliberately does not
   round (app/service.py), so the trade column always sums to the summary. The
   cost is exponent noise: 55.8810 next to 17.772750 next to -20.00.

   Trim the padding zeros, never the value. Rounding here would be the one
   change that breaks the sum, and a verification UI that quietly drops a digit
   is worse than an untidy one. Two decimals minimum so it still reads as money;
   anything longer is real precision, not padding. */
function money(s) {
  if (s == null) return "—";
  const str = String(s);
  if (!/^-?\d+(\.\d+)?$/.test(str)) return str;
  const [whole, frac = ""] = str.split(".");
  return whole + "." + frac.replace(/0+$/, "").padEnd(2, "0");
}

function formatTime(t) {
  const d = new Date(t * 1000);
  return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) +
    " " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + ":" + pad(d.getUTCSeconds());
}

function formatTick(t) {
  const d = new Date(t * 1000);
  return pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate());
}

/* ---------------------------------- chart scaffolding ---------------------------------- */

function setupChart() {
  if (state.chart) return;

  const chart = LightweightCharts.createChart(el.chartEl, {
    width: el.chartbox.clientWidth || 800,
    height: el.chartbox.clientHeight || 400,
    layout: {
      background: { type: LightweightCharts.ColorType.Solid, color: "transparent" },
      textColor: "#6B7C8F",
      fontFamily: "'IBM Plex Mono', ui-monospace, Menlo, monospace",
      fontSize: 11,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: "rgba(30, 42, 56, .55)" },
      horzLines: { color: "rgba(30, 42, 56, .55)" },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: "rgba(232, 163, 61, .35)", labelBackgroundColor: "#121821" },
      horzLine: { color: "rgba(232, 163, 61, .35)", labelBackgroundColor: "#121821" },
    },
    rightPriceScale: {
      borderColor: "#1E2A38",
      scaleMargins: { top: 0.07, bottom: 0.05 },
    },
    leftPriceScale: {
      visible: false, // turned on per-run only when the payload has a pane indicator
      borderColor: "#1E2A38",
      scaleMargins: { top: 0.72, bottom: 0.04 },
      minimumWidth: 44,
    },
    timeScale: {
      borderColor: "#1E2A38",
      rightOffset: 6,
      fixLeftEdge: true,
      fixRightEdge: true,
    },
    handleScroll: { vertTouchDrag: false },
    localization: {
      dateFormat: "yyyy-MM-dd",
      timeFormatter: (t) => (typeof t === "number" ? formatTime(t) : String(t)),
      tickMarkFormatter: (t) => (typeof t === "number" ? formatTick(t) : String(t)),
    },
  });

  state.main = chart.addCandlestickSeries({
    upColor: "#4FB286",
    downColor: "#D2544F",
    borderVisible: false,
    wickUpColor: "#4FB286",
    wickDownColor: "#D2544F",
  });

  state.chart = chart;
  chart.timeScale().subscribeVisibleLogicalRangeChange(() => scheduleShroud());

  // ResizeObserver rather than a window listener: the box also changes size when
  // the rail reflows above the chart, which fires no resize event.
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => {
      resizeChart();
      updateShroud();
    }).observe(el.chartbox);
  } else {
    let resizeId = null;
    window.addEventListener("resize", () => {
      clearTimeout(resizeId);
      resizeId = setTimeout(() => { resizeChart(); updateShroud(); }, 150);
    });
  }
}

function resizeChart() {
  if (!state.chart) return;
  const w = el.chartbox.clientWidth;
  const h = el.chartbox.clientHeight;
  if (w > 0 && h > 0) state.chart.applyOptions({ width: w, height: h });
}

/* ---------------------------------- warmup shroud ---------------------------------- */

function scheduleShroud() {
  clearTimeout(state.shroudTimer);
  state.shroudTimer = setTimeout(updateShroud, SHROUD_MS);
}

function updateShroud() {
  const chart = state.chart;
  if (!chart || !state.result) {
    hideShroud();
    return;
  }
  const logical = state.result.warmup.bars;
  const px = chart.timeScale().logicalToCoordinate(logical);
  if (px == null) {
    hideShroud();
    return;
  }
  // logicalToCoordinate is relative to the price pane, not the widget: the price
  // scale gutters have to be subtracted or the amber line lands off the boundary.
  const leftW = scaleWidth("left");
  const rightW = scaleWidth("right");
  el.layer.style.left = leftW + "px";
  el.layer.style.right = rightW + "px";

  const boxW = Math.max(0, el.chartbox.clientWidth - leftW - rightW);
  const boxH = el.chartbox.clientHeight;
  if (boxW <= 0 || boxH <= 0) return;

  // Boundary scrolled off to the left: nothing on screen is warmup, so drawing a
  // zero-width band would leave a stray amber edge at x=0.
  const onScreen = px > 0;
  el.shroud.style.display = onScreen ? "block" : "none";
  el.shroud.style.width = Math.max(0, px) + "px";
  el.armedLine.hidden = !onScreen;
  el.armedLabel.hidden = !onScreen;
  el.armedBar.textContent = logical + " bar" + (logical === 1 ? "" : "s");
  el.armedLine.style.left = px + "px";
  el.armedLabel.style.left = px + "px";
  el.armedLabel.classList.toggle("flip", px + 120 > boxW);

  const hasPane = !!state.rsiSeries;
  const ruleY = hasPane ? boxH * 0.72 : -1;
  el.paneRule.hidden = !hasPane;
  el.paneTag.hidden = !hasPane;
  if (hasPane) {
    el.paneRule.style.top = ruleY + "px";
    el.paneTag.style.top = (ruleY + 4) + "px";
    el.paneTag.textContent = "RSI · 30 / 70";
  }
}

// v4 throws "Value is null" from priceScale(id).width() when that scale has no
// series attached (the left scale, on any strategy without a pane indicator).
function scaleWidth(id) {
  try {
    return state.chart.priceScale(id).width();
  } catch (_) {
    return 0;
  }
}

function hideShroud() {
  el.shroud.style.display = "none";
  el.armedLine.hidden = true;
  el.armedLabel.hidden = true;
  el.paneRule.hidden = true;
  el.paneTag.hidden = true;
}

/* ---------------------------------- series render ---------------------------------- */

function createRsiSeries() {
  const chart = state.chart;
  const rsi = chart.addLineSeries({
    color: COLORS.trace,
    lineWidth: 2,
    priceScaleId: "left",
    priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    autoscaleInfoProvider: (orig) => ({ priceRange: { minValue: 0, maxValue: 100 } }),
    lastValueVisible: false,
    priceLineVisible: false,
  });
  chart.priceScale("left").applyOptions({ autoScale: true, mode: LightweightCharts.PriceScaleMode.Normal });
  [30, 70].forEach((p) => {
    rsi.createPriceLine({
      price: p,
      color: "rgba(107, 124, 143, .7)",
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: false,
      title: "",
    });
  });
  return rsi;
}

function renderSeries(r) {
  const chart = state.chart;

  // Drop everything from the previous run.
  state.indicatorLines.forEach((s) => chart.removeSeries(s));
  state.indicatorLines = [];
  if (state.rsiSeries) chart.removeSeries(state.rsiSeries);
  state.rsiSeries = null;
  clearBracket();

  // Candles.
  state.main.setData(r.candles.map((c) => ({
    time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
  })));

  // Indicators: each one its own series. RSI-style panes go to the bottom band.
  const hasPane = r.indicators.some((ind) => ind.pane);
  chart.applyOptions({
    rightPriceScale: { scaleMargins: { top: 0.07, bottom: hasPane ? 0.28 : 0.05 } },
    leftPriceScale: { visible: hasPane },
  });
  r.indicators.forEach((ind) => {
    const data = ind.data.map((d) => ({ time: d.time, value: d.value }));
    if (ind.pane) {
      state.rsiSeries = createRsiSeries();
      state.rsiSeries.setData(data);
    } else {
      const line = chart.addLineSeries({
        color: "#5FB3D9",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      line.setData(data);
      state.indicatorLines.push(line);
    }
  });
}

function setMarkers(r) {
  state.markers = [];
  r.markers.forEach((m) => {
    const isEntry = m.kind === "entry";
    const color = isEntry
      ? (m.won === false ? "#D2544F" : m.won ? "#4FB286" : COLORS.trace)
      : (m.straddle ? COLORS.trace : m.won ? "#4FB286" : "#D2544F");
    state.markers.push({
      time: m.time,
      position: isEntry ? "aboveBar" : "belowBar",
      color,
      shape: isEntry ? "arrowUp" : "arrowDown",
      text: isEntry ? "entry" : m.straddle ? "straddle" : m.kind,
      size: 1,
    });
  });
  state.main.setMarkers(state.markers);
}

/* ---------------------------------- spec / summary ---------------------------------- */

function setSpec(r) {
  const p = r.strategy;
  el.specSymbol.textContent = [p.symbol, p.exchange].filter(Boolean).join(" · ") || "—";
  el.specEntry.textContent = p.entry || "—";
  el.specStop.textContent = (p.stop_loss_pct != null ? p.stop_loss_pct : "—") + "%";
  el.specRR.textContent = p.risk_reward_ratio != null ? p.risk_reward_ratio + ":1" : "—";
  el.specRange.textContent = r.range.from + "  →  " + r.range.to;
  el.warmSkipped.textContent = r.warmup.bars + " bar" + (r.warmup.bars === 1 ? "" : "s");
  el.warmArmed.textContent = formatTime(r.warmup.time);
  el.headSymbol.textContent = p.symbol;
  el.headInterval.textContent = r.strategy.interval;
  el.headBars.textContent = r.range.bars;
}

function setSummary(s) {
  el.sumClosed.textContent = s.closed;
  el.sumWins.textContent = s.wins;
  el.sumLosses.textContent = s.losses;
  el.sumNet.textContent = money(s.net);
  el.sumOpen.textContent = s.open;
}

/* ---------------------------------- trade log ---------------------------------- */

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function cell(cls, content) {
  return "<td class=\"" + esc(cls) + "\">" + (content == null ? "" : content) + "</td>";
}

function renderTrades(r) {
  const rows = [];

  r.trades.forEach((t, i) => {
    const tr = document.createElement("tr");
    tr.tabIndex = 0;
    tr.dataset.i = String(i);
    tr.dataset.entry = String(t.entry_time);
    tr.dataset.exit = String(t.exit_time);
    tr.title = (t.straddle
      ? "Straddle bar: the range hit BOTH the stop and the target; the engine's " +
        "stop-before-target rule booked it as the loss.\n"
      : "") +
      "Activate to frame this trade on the chart.";

    const reasonCls = t.exit_reason === "target" ? "target" : t.exit_reason === "stop_loss" ? "stop_loss" : "";
    tr.innerHTML =
      cell("i", String(i + 1)) +
      cell("t", formatTime(t.entry_time)) +
      cell("n", esc(money(t.entry_price))) +
      cell("t", formatTime(t.exit_time)) +
      cell("n", esc(money(t.exit_price))) +
      cell("n", '<span class="reason ' + reasonCls + '">' + esc(t.exit_reason) + "</span>") +
      cell("n pnl " + (t.won ? "win" : "loss"), esc(money(t.pnl))) +
      cell("f", t.straddle
        ? '<span class="flag" tabindex="0" aria-label="straddle bar">⚠</span>'
        : "");

    tr.addEventListener("click", () => focusTrade(i, tr));
    tr.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        focusTrade(i, tr);
      }
    });
    rows.push(tr);
  });

  r.open.forEach((o, i) => {
    const tr = document.createElement("tr");
    tr.className = "open";
    tr.tabIndex = 0;
    tr.dataset.entry = String(o.entry_time);
    tr.title = "Open position — the engine is still holding it. Activate to frame it.";
    tr.innerHTML =
      cell("i", String(r.trades.length + i + 1)) +
      cell("t", formatTime(o.entry_time)) +
      cell("n", esc(money(o.entry_price))) +
      cell("t", "—") +
      cell("n", "—") +
      cell("n", '<span class="reason">open</span>') +
      cell("n", "—") +
      cell("f", "");
    tr.addEventListener("click", () => focusOpen(o, tr));
    tr.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        focusOpen(o, tr);
      }
    });
    rows.push(tr);
  });

  el.tbody.replaceChildren(...rows);

  if (!rows.length) {
    el.logNote.textContent = "No trades. The strategy fired no signals in this window.";
  } else {
    el.logNote.textContent = r.trades.length + " closed" +
      (r.open.length ? ", " + r.open.length + " open" : "") +
      " — activate a row to frame the trade.";
  }
}

function selectRow(tr) {
  if (state.selectedRow && state.selectedRow !== tr) {
    state.selectedRow.removeAttribute("aria-selected");
  }
  state.selectedRow = tr;
  if (tr) tr.setAttribute("aria-selected", "true");
}

/* ---------------------------------- trade framing ---------------------------------- */

function markerIndex(time, predicate) {
  return state.markers.findIndex((m) => m.time === time && predicate(m));
}

function flipEntryUp(time) {
  const idx = markerIndex(time, (m) => m.text === "entry");
  if (idx >= 0 && state.markers[idx].shape === "arrowDown") {
    state.markers[idx] = Object.assign({}, state.markers[idx],
      { position: "aboveBar", shape: "arrowUp" });
    state.main.setMarkers(state.markers.slice());
  }
}

function flipExitDown(time) {
  const idx = markerIndex(time, (m) => m.text !== "entry");
  if (idx >= 0 && state.markers[idx].shape === "arrowUp") {
    state.markers[idx] = Object.assign({}, state.markers[idx],
      { position: "belowBar", shape: "arrowDown" });
    state.main.setMarkers(state.markers.slice());
  }
}

function focusTrade(i, tr) {
  const t = state.result.trades[i];
  if (!t) return;
  selectRow(tr);
  flipEntryUp(t.entry_time);
  flipExitDown(t.exit_time);
  drawBracket(parseFloat(t.entry_price), parseFloat(t.stop_loss), parseFloat(t.target));
  frameRange(t.entry_time, t.exit_time);
  el.logNote.textContent = "Framing trade #" + (i + 1) +
    " — " + formatTime(t.entry_time) + " → " + formatTime(t.exit_time) +
    (t.straddle ? "  ⚠ straddle bar (stop and target both hit)" : "");
}

function focusOpen(o, tr) {
  selectRow(tr);
  flipEntryUp(o.entry_time);
  drawBracket(parseFloat(o.entry_price), parseFloat(o.stop_loss), parseFloat(o.target));
  const logical = state.result.candles.findIndex((c) => c.time === o.entry_time);
  if (logical >= 0) {
    state.chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, logical - TRADE_PAD),
      to: logical + TRADE_PAD,
    });
  }
  el.logNote.textContent = "Framing open position — " + formatTime(o.entry_time);
}

/* Bracket lines hang on the candlestick series so they sit on the price axis. */
function clearBracket() {
  state.priceLines.forEach((pl) => state.main.removePriceLine(pl));
  state.priceLines = [];
}

function drawBracket(entry, stop, target) {
  clearBracket();
  if (entry == null) return;
  const push = (price, color, title) => {
    state.priceLines.push(state.main.createPriceLine({
      price,
      color,
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title,
    }));
  };
  if (stop != null) push(stop, "#D2544F", "STOP");
  if (target != null) push(target, "#4FB286", "TGT");
  if (entry != null && (stop != null || target != null)) push(entry, "rgba(201, 212, 224, .8)", "ENTRY");
}

function frameRange(entryTime, exitTime) {
  const candles = state.result.candles;
  let from = null;
  let to = null;
  for (let i = 0; i < candles.length; i++) {
    if (candles[i].time === entryTime) from = i;
    if (candles[i].time === exitTime) to = i;
  }
  if (from == null || to == null) return;
  const start = Math.max(0, from - TRADE_PAD);
  const end = Math.min(candles.length - 1, to + TRADE_PAD);
  state.chart.timeScale().setVisibleLogicalRange({ from: start, to: end });
}

/* ---------------------------------- backtest run ---------------------------------- */

function clampBars(n) {
  if (Number.isNaN(n)) return 500;
  return Math.max(1, Math.min(20000, n));
}

async function runBacktest() {
  const strategy = el.strategy.value;
  const interval = el.interval.value;
  const bars = clampBars(parseInt(el.bars.value, 10));

  if (!strategy || !interval) {
    setError("No strategy loaded — is /api/strategies reachable?");
    return;
  }
  setError(null);
  setBusy(true, "Fetching " + bars + " bars from the live feed…");

  let done = "";
  try {
    const r = await getJSON(backtestUrl(strategy, interval, bars));
    renderResult(r);
    done = r.candles.length + " bars · " + r.summary.closed + " closed · " + r.summary.open + " open";
  } catch (err) {
    setError(err.message);
    $log(err);
    done = "Run failed — see the readout above.";
  } finally {
    setBusy(false, done);
  }
}

function renderResult(r) {
  state.result = r;
  setupChart();
  resizeChart();
  renderSeries(r);
  setMarkers(r);
  setSpec(r);
  setSummary(r.summary);
  renderTrades(r);
  setError(null);

  // Show the whole run: the warmup shroud is the point of this instrument, so
  // the armed boundary must be on screen before the user touches anything.
  const n = r.candles.length;
  if (n > 0) {
    state.chart.timeScale().setVisibleLogicalRange({ from: 0, to: n - 1 });
  }
  updateShroud();
}

/* ---------------------------------- boot ---------------------------------- */

async function boot() {
  try {
    const data = await getJSON(new URL("/api/strategies", document.baseURI).toString());
    const strategies = Array.isArray(data.strategies) ? data.strategies : [];
    state.intervals = Array.isArray(data.intervals) ? data.intervals : [];

    strategies.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.path;
      opt.textContent = (s.name || s.path) + "  —  " + (s.symbol || "");
      if (s.error) opt.textContent += "  (⚠ " + s.error + ")";
      el.strategy.appendChild(opt);
    });
    if (!el.strategy.options.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No strategies found";
      el.strategy.appendChild(opt);
    }

    (state.intervals.length ? state.intervals : [DEFAULT_INTERVAL]).forEach((iv) => {
      const opt = document.createElement("option");
      opt.value = iv;
      opt.textContent = iv;
      el.interval.appendChild(opt);
    });
    // Daily is the sane default; the API's interval order starts at 1m, which
    // would auto-run an intraday window nobody asked for.
    if (state.intervals.includes(DEFAULT_INTERVAL)) el.interval.value = DEFAULT_INTERVAL;

    el.controls.addEventListener("submit", (ev) => {
      ev.preventDefault();
      runBacktest();
    });

    // Auto-run the first strategy on load.
    runBacktest();
  } catch (err) {
    setError(err.message);
    setBusy(false);
  }
}

boot();
