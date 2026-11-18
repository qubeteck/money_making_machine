const $ = (id) => document.getElementById(id);
const API = "/api/advanced";
let equityChart;
let allocationChart;
let candleData = [];
let symbolsLoaded = false;
let lastAllocationKey = "";
let lastSnapshotKey = "";
let stream;

const CHART_COLORS = ["#2dd4a7", "#60a5fa", "#f59e0b", "#a78bfa", "#fb7185", "#34d399"];

async function api(path) {
  const response = await fetch(path);
  if (!response.ok) {
    let detail = `API ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* keep the status message */
    }
    throw new Error(detail);
  }
  return response.json();
}

async function apiPost(path) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    let detail = `API ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* keep the status message */
    }
    throw new Error(detail);
  }
  return response.json();
}

const money = (value) =>
  "$" +
  Number(value || 0).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

const signedMoney = (value) => {
  const number = Number(value || 0);
  return `${number >= 0 ? "+" : "-"}$${Math.abs(number).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

const price = (value) => {
  const number = Number(value);
  if (!number) return "—";
  if (Math.abs(number) >= 1000) {
    return number.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (Math.abs(number) >= 1) return number.toFixed(4);
  return number.toFixed(6);
};

const axisPrice = (value) =>
  Math.abs(value) >= 1000
    ? Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 })
    : Number(value).toFixed(2);

const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character]
  );

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function emptyRow(columns, message) {
  return `<tr><td colspan="${columns}" class="empty">${message}</td></tr>`;
}

function populateSymbols(symbols, defaultTimeframe) {
  if (symbolsLoaded || !Array.isArray(symbols) || !symbols.length) return;
  const select = $("symbolSelect");
  select.innerHTML = "";
  for (const symbol of symbols) {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    select.appendChild(option);
  }
  const timeframe = $("tfSelect");
  if (defaultTimeframe && Array.from(timeframe.options).some((option) => option.value === defaultTimeframe)) {
    timeframe.value = defaultTimeframe;
  }
  symbolsLoaded = true;
}

function renderOverview(data) {
  setText("balance", money(data.balance));
  setText("equity", money(data.equity));
  setText("pnl", signedMoney(data.daily_pnl));
  $("pnl").className = `text-2xl font-bold mt-3 ${data.daily_pnl >= 0 ? "positive" : "negative"}`;
  setText("pnlPct", `${data.daily_pnl_pct >= 0 ? "+" : ""}${data.daily_pnl_pct}% today · realized`);
  $("pnlPct").className = `text-xs mt-2 ${data.daily_pnl_pct >= 0 ? "positive" : "negative"}`;
  setText("winRate", `${data.win_rate}%`);
  setText(
    "winMeta",
    data.trades
      ? `${data.trades} closed · max drawdown ${data.drawdown}%`
      : "No closed trades yet"
  );
  setText("updatedAt", `Updated ${new Date(data.updated_at).toLocaleTimeString()}`);
  setText("engineStatus", data.paused ? "Engine paused" : "Engine running");
  setText(
    "modeText",
    data.mode === "LIVE" ? "Live execution · real orders" : "Paper trading · no real orders"
  );

  $("engineDot").className = `w-2 h-2 rounded-full ${data.paused ? "bg-amber-400" : "bg-emerald-400"}`;

  const badge = $("modeBadge");
  badge.textContent = `● ${data.mode}`;
  badge.className =
    "tag border " +
    (data.mode === "LIVE"
      ? "bg-rose-400/15 text-rose-300 border-rose-400/20"
      : "bg-amber-400/15 text-amber-300 border-amber-400/20");

  setText("equityTag", data.mode === "LIVE" ? "LIVE ACCOUNT" : "PAPER ACCOUNT");
  setText("positionCount", `${data.open_positions} OPEN`);
  setText("signalCount", `${data.signals_today} TODAY`);

  populateSymbols(data.symbols, data.entry_timeframe);
  return data;
}

function renderMarkets(rows) {
  setText("marketCount", `${rows.length} INSTRUMENTS`);
  $("marketRows").innerHTML = rows.length
    ? rows
        .map(
          (row) => `<tr class="border-b border-slate-800/80">
            <td class="py-4"><div class="font-semibold">${escapeHtml(row.symbol)}</div><div class="text-xs muted">MEXC futures</div></td>
            <td class="text-right font-medium">${price(row.price)}</td>
            <td class="text-right muted">${escapeHtml(row.trend)}</td>
            <td class="text-right muted">${escapeHtml(row.structure || "—")}</td>
            <td class="text-right text-sky-300">${row.score ? row.score.toFixed(1) : "—"}</td>
            <td class="text-right text-xs muted">${escapeHtml(row.status)}</td>
          </tr>`
        )
        .join("")
    : emptyRow(6, "No scan results yet. Wait for the engine to complete a scan.");
}

function renderPositions(rows) {
  setText("positionCount", `${rows.length} OPEN`);
  $("positionRows").innerHTML = rows.length
    ? rows
        .map(
          (row) => `<tr class="border-b border-slate-800/80">
            <td class="py-4 font-semibold">${escapeHtml(row.symbol)}</td>
            <td class="${row.side === "BUY" ? "positive" : "negative"}">${row.side}</td>
            <td>${price(row.entry)}</td>
            <td>${price(row.current)}</td>
            <td class="muted">${price(row.sl)}</td>
            <td class="muted">${price(row.tp)}</td>
            <td class="muted">${row.risk}</td>
            <td class="text-right font-semibold ${row.pnl >= 0 ? "positive" : "negative"}">${signedMoney(row.pnl)}</td>
          </tr>`
        )
        .join("")
    : emptyRow(8, "No open positions.");
}

function renderSignals(rows) {
  $("signalRows").innerHTML = rows.length
    ? rows
        .map(
          (row) => `<tr class="border-b border-slate-800/80">
            <td class="py-4 muted">${escapeHtml(row.time)}</td>
            <td class="font-semibold">${escapeHtml(row.symbol)}</td>
            <td class="${row.side === "BUY" ? "positive" : "negative"}">${row.side}</td>
            <td>${escapeHtml(row.strategy)}</td>
            <td class="muted">${escapeHtml(row.tf)}</td>
            <td><span class="text-sky-300">${row.confidence}/100</span></td>
            <td><span class="tag bg-amber-400/10 text-amber-300">${escapeHtml(row.status)}</span></td>
          </tr>`
        )
        .join("")
    : emptyRow(7, "No signals generated yet.");
}

function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (value < 1) return `${Math.round(value * 1000)}ms`;
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const remainder = Math.round(value % 60);
  if (minutes < 60) return `${minutes}m ${remainder}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function formatJobTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function jobStatusClass(status) {
  if (status === "error") return "bg-rose-400/15 text-rose-300";
  if (status === "skipped") return "bg-amber-400/15 text-amber-300";
  return "bg-emerald-400/15 text-emerald-300";
}

function renderJobs(jobs) {
  setText("jobCount", `${jobs.length} RECENT`);
  $("jobRows").innerHTML = jobs.length
    ? jobs
        .map(
          (row) => `<tr class="border-b border-slate-800/80">
            <td class="py-4 font-semibold">${escapeHtml(row.job_name)}</td>
            <td class="muted text-xs">${escapeHtml(formatJobTime(row.started_at))}</td>
            <td><span class="tag ${jobStatusClass(row.status)}">${escapeHtml(row.status)}</span>${row.attempts > 1 ? `<span class="text-xs muted ml-1">×${row.attempts}</span>` : ""}</td>
            <td class="text-right muted">${formatDuration(row.duration_seconds)}</td>
            <td class="muted text-xs">${escapeHtml(row.message || "—")}</td>
          </tr>`
        )
        .join("")
    : emptyRow(5, "No jobs recorded yet. The first scheduled scan will appear here.");
}

function renderOperations(metrics) {
  setText("uptime", formatDuration(metrics.uptime_seconds));
  setText("jobErrors", metrics.jobs_errors_24h ?? 0);
  setText("botErrors", metrics.bot_errors_24h ?? 0);
  setText("schedulerStatus", metrics.scheduler_running ? "Running" : "Stopped");

  const badge = $("runtimeStatus");
  badge.textContent = metrics.scheduler_running ? "● ONLINE" : "● STOPPED";
  badge.className =
    "tag border " +
    (metrics.scheduler_running
      ? "bg-emerald-400/15 text-emerald-300 border-emerald-400/20"
      : "bg-rose-400/15 text-rose-300 border-rose-400/20");
  $("schedulerStatus").className = `font-semibold mt-1 ${
    metrics.scheduler_running ? "positive" : "negative"
  }`;
}

async function loadOperations() {
  const [metrics, jobs] = await Promise.all([
    api("/api/v1/metrics"),
    api("/api/v1/jobs?limit=6"),
  ]);
  renderOperations(metrics);
  renderJobs(jobs.jobs || []);
}

async function triggerScan() {
  const button = $("scanBtn");
  button.disabled = true;
  setText("scanMessage", "Scan running…");
  try {
    const result = await apiPost("/api/v1/jobs/scan");
    const summary =
      result.status === "skipped"
        ? result.result?.reason || "Scan skipped"
        : `Evaluated ${result.result?.evaluated ?? 0} setups · opened ${result.result?.opened ?? 0}`;
    setText("scanMessage", summary);
    await refresh(false);
  } catch (error) {
    setText("scanMessage", `Scan failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function renderEquity(equity) {
  if (equityChart) equityChart.destroy();
  equityChart = new Chart($("equityChart"), {
    type: "line",
    data: {
      labels: equity.labels,
      datasets: [
        {
          label: "Equity",
          data: equity.values,
          borderColor: "#2dd4a7",
          backgroundColor: "rgba(45,212,167,.10)",
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: "#8293aa", maxTicksLimit: 7 },
          grid: { display: false },
        },
        y: {
          ticks: { color: "#8293aa", callback: (value) => "$" + Number(value).toLocaleString() },
          grid: { color: "rgba(148,163,184,.10)" },
        },
      },
    },
  });
}

function renderAllocation(allocation) {
  const key = JSON.stringify(allocation);
  if (key === lastAllocationKey) return;
  lastAllocationKey = key;

  if (allocationChart) allocationChart.destroy();
  allocationChart = new Chart($("allocationChart"), {
    type: "doughnut",
    data: {
      labels: allocation.labels,
      datasets: [
        {
          data: allocation.values,
          backgroundColor: allocation.labels.map(
            (_, index) => CHART_COLORS[index % CHART_COLORS.length]
          ),
          borderWidth: 0,
          hoverOffset: 5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "72%",
      plugins: { legend: { display: false } },
    },
  });

  $("allocationLegend").innerHTML = allocation.labels
    .map(
      (label, index) =>
        `<span><span style="color:${CHART_COLORS[index % CHART_COLORS.length]}">●</span> ${escapeHtml(label)}</span>`
    )
    .join("");
}

async function loadOverview() {
  const data = await api(`${API}/overview`);
  renderOverview(data);
  return data;
}

async function loadMarkets() {
  renderMarkets(await api(`${API}/markets`));
}

async function loadPositions() {
  renderPositions(await api(`${API}/positions`));
}

async function loadSignals() {
  renderSignals(await api(`${API}/signals`));
}

async function loadCharts() {
  const [equity, allocation] = await Promise.all([
    api(`${API}/equity`),
    api(`${API}/allocation`),
  ]);
  renderEquity(equity);
  renderAllocation(allocation);
}

function applySnapshot(snapshot) {
  const key = JSON.stringify(snapshot);
  if (key === lastSnapshotKey) return;
  lastSnapshotKey = key;
  if (snapshot.overview) renderOverview(snapshot.overview);
  if (snapshot.markets) renderMarkets(snapshot.markets);
  if (snapshot.positions) renderPositions(snapshot.positions);
  if (snapshot.signals) renderSignals(snapshot.signals);
  if (snapshot.allocation) renderAllocation(snapshot.allocation);
  if (snapshot.server_time) {
    setText("updatedAt", `Updated ${new Date(snapshot.server_time).toLocaleTimeString()}`);
  }
}

function connectStream() {
  const dot = $("streamDot");
  if (!window.EventSource) {
    setText("streamStatus", "Polling mode");
    if (dot) dot.className = "w-2 h-2 rounded-full bg-amber-400";
    return;
  }

  stream = new EventSource(`${API}/stream`);
  stream.addEventListener("open", () => {
    setText("streamStatus", "Live stream connected");
    if (dot) dot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
  });
  stream.addEventListener("snapshot", (event) => {
    try {
      applySnapshot(JSON.parse(event.data));
    } catch (error) {
      console.error("Could not apply live snapshot", error);
    }
  });
  stream.addEventListener("server_error", (event) => {
    console.error("Live stream error", event.data);
    setText("streamStatus", "Live stream error");
    if (dot) dot.className = "w-2 h-2 rounded-full bg-rose-400";
  });
  stream.addEventListener("error", () => {
    setText("streamStatus", "Stream reconnecting…");
    if (dot) dot.className = "w-2 h-2 rounded-full bg-amber-400";
  });
}

async function loadCandles() {
  const symbol = $("symbolSelect").value;
  if (!symbol) return;
  const errorBox = $("candleError");
  errorBox.classList.add("hidden");

  try {
    const data = await api(
      `${API}/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(
        $("tfSelect").value
      )}`
    );
    candleData = data.candles || [];
    drawCandles();
  } catch (error) {
    candleData = [];
    drawCandles();
    errorBox.textContent = error.message;
    errorBox.classList.remove("hidden");
  }
}

function drawCandles() {
  const canvas = $("candleCanvas");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, rect.width * dpr);
  canvas.height = Math.max(1, rect.height * dpr);
  const context = canvas.getContext("2d");
  context.scale(dpr, dpr);

  const width = rect.width;
  const height = rect.height;
  const pad = { left: 12, right: 70, top: 12, bottom: 22 };
  const chartWidth = width - pad.left - pad.right;
  const chartHeight = height - pad.top - pad.bottom;
  context.clearRect(0, 0, width, height);
  if (!candleData.length) return;

  const low = Math.min(...candleData.map((candle) => candle.low));
  const high = Math.max(...candleData.map((candle) => candle.high));
  const range = high - low || 1;
  const y = (value) => pad.top + ((high - value) / range) * chartHeight;

  context.font = "10px system-ui";
  context.fillStyle = "#8293aa";
  context.strokeStyle = "rgba(148,163,184,.13)";
  for (let index = 0; index <= 4; index += 1) {
    const lineY = pad.top + (chartHeight * index) / 4;
    context.beginPath();
    context.moveTo(pad.left, lineY);
    context.lineTo(width - pad.right, lineY);
    context.stroke();
    const value = high - (range * index) / 4;
    context.fillText(axisPrice(value), width - pad.right + 8, lineY + 3);
  }

  const step = chartWidth / candleData.length;
  const body = Math.max(3, step * 0.58);
  candleData.forEach((candle, index) => {
    const x = pad.left + index * step + step / 2;
    const up = candle.close >= candle.open;
    const color = up ? "#2dd4a7" : "#fb7185";
    context.strokeStyle = color;
    context.fillStyle = color;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(x, y(candle.high));
    context.lineTo(x, y(candle.low));
    context.stroke();
    const top = Math.min(y(candle.open), y(candle.close));
    const candleHeight = Math.max(1, Math.abs(y(candle.open) - y(candle.close)));
    context.fillRect(x - body / 2, top, body, candleHeight);
  });

  context.beginPath();
  context.strokeStyle = "#2dd4a7";
  context.lineWidth = 1.5;
  candleData.forEach((candle, index) => {
    const slice = candleData.slice(Math.max(0, index - 19), index + 1);
    const average = slice.reduce((sum, item) => sum + item.close, 0) / slice.length;
    const x = pad.left + index * step + step / 2;
    if (index) context.lineTo(x, y(average));
    else context.moveTo(x, y(average));
  });
  context.stroke();
}

async function refresh(includeCandles = true) {
  const button = $("refreshBtn");
  button.disabled = true;
  try {
    await loadOverview();
    await Promise.all([
      loadMarkets(),
      loadPositions(),
      loadSignals(),
      loadCharts(),
      loadOperations(),
    ]);
    if (includeCandles) await loadCandles();
  } catch (error) {
    console.error(error);
    setText("engineStatus", "API error");
    $("engineDot").className = "w-2 h-2 rounded-full bg-rose-400";
    const errorBox = $("candleError");
    errorBox.textContent = `Could not load dashboard data: ${error.message}`;
    errorBox.classList.remove("hidden");
  } finally {
    button.disabled = false;
  }
}

$("refreshBtn").addEventListener("click", () => refresh());
$("scanBtn").addEventListener("click", triggerScan);
$("symbolSelect").addEventListener("change", loadCandles);
$("tfSelect").addEventListener("change", loadCandles);
window.addEventListener("resize", () => {
  if (candleData.length) drawCandles();
});

refresh();
connectStream();
setInterval(() => {
  if (!document.hidden) refresh(false);
}, 60000);
