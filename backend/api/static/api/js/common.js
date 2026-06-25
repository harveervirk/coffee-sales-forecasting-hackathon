/**
 * common.js – Shared utilities for the CanAI Cafe Intelligence portal.
 * Loaded on every page before any page-specific script.
 */

/* ----------------------------------------------------------
   API helpers
   ---------------------------------------------------------- */
async function fetchAPI(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    const err = new Error(`HTTP ${resp.status} from ${url}`);
    err.status = resp.status;
    throw err;
  }
  return resp.json();
}

/* ----------------------------------------------------------
   Formatting
   ---------------------------------------------------------- */
function formatCAD(value) {
  return new Intl.NumberFormat('en-CA', {
    style: 'currency', currency: 'CAD',
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(value);
}

function formatCADFull(value) {
  return new Intl.NumberFormat('en-CA', {
    style: 'currency', currency: 'CAD',
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value);
}

function formatNum(value) {
  return new Intl.NumberFormat('en-CA').format(value);
}

function formatPct(value, decimals = 1) {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${Number(value).toFixed(decimals)}%`;
}

function growthClass(value) {
  return value >= 0 ? 'growth-positive' : 'growth-negative';
}

function growthIcon(value) {
  return value >= 0 ? 'bi-arrow-up-right' : 'bi-arrow-down-right';
}

/* ----------------------------------------------------------
   State renderers
   ---------------------------------------------------------- */
function showLoading(id, msg = 'Loading…') {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `
    <div class="loading-state" role="status" aria-label="${msg}">
      <div class="spinner-border spinner-border-sm text-coffee" style="width:1.1rem;height:1.1rem;"></div>
      <span class="text-muted">${msg}</span>
    </div>`;
}

function showError(id, msg = 'Could not load data.', icon = 'bi-exclamation-triangle-fill') {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `
    <div class="error-state" role="alert">
      <i class="bi ${icon}"></i>${msg}
    </div>`;
}

function show503(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `
    <div class="warn-box">
      <i class="bi bi-clock-history me-2"></i>
      <strong>Forecast data not ready.</strong>
      Run <code>python backend/manage.py generate_sales_forecast</code> to generate it.
    </div>`;
}

function showEmpty(id, msg = 'No data available.') {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `
    <div class="empty-state" role="status">
      <i class="bi bi-inbox" aria-hidden="true"></i>
      <span>${msg}</span>
    </div>`;
}

/* ----------------------------------------------------------
   Chart registry – safely destroy before re-creating
   ---------------------------------------------------------- */
const _charts = {};

function destroyChart(id) {
  if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
}

function registerChart(id, chart) {
  destroyChart(id);
  _charts[id] = chart;
  return chart;
}

/* ----------------------------------------------------------
   Shared Chart.js palette and defaults
   ---------------------------------------------------------- */
const COLORS = {
  coffee:   '#6F4E37',
  coffeeAlt:'#3D1C02',
  amber:    '#D2691E',
  amberLight:'rgba(210,105,30,0.15)',
  green:    '#15803D',
  blue:     '#1D4ED8',
  red:      '#B91C1C',
  purple:   '#7C3AED',
  teal:     '#0F766E',
  slate:    '#475569',
};

const PALETTE = [
  '#6F4E37','#D2691E','#15803D','#1D4ED8','#7C3AED',
  '#0F766E','#B45309','#DC2626','#0369A1','#6D28D9',
];

function chartFont() {
  return { family: "'Inter','Segoe UI',system-ui,sans-serif", size: 12 };
}

// Apply global Chart.js defaults
if (typeof Chart !== 'undefined') {
  Chart.defaults.font = chartFont();
  Chart.defaults.plugins.legend.labels.font = chartFont();
  Chart.defaults.plugins.tooltip.titleFont = { ...chartFont(), weight: '600' };
  Chart.defaults.plugins.tooltip.bodyFont  = chartFont();
  Chart.defaults.color = '#6B7280';
}

function lineDefaults(color = COLORS.coffee) {
  return {
    borderColor: color,
    backgroundColor: color + '22',
    tension: 0.35,
    pointRadius: 3,
    pointHoverRadius: 6,
    borderWidth: 2,
    fill: false,
  };
}

function barDefaults(colors) {
  return {
    backgroundColor: colors || PALETTE.map(c => c + 'CC'),
    borderColor: 'transparent',
    borderRadius: 5,
    borderSkipped: false,
  };
}

function commonScales(xLabel = '', yLabel = '', isCurrency = false) {
  return {
    x: {
      grid: { display: false },
      ticks: { font: chartFont(), maxRotation: 30 },
      title: xLabel ? { display: true, text: xLabel, font: { ...chartFont(), size: 11 } } : {},
    },
    y: {
      grid: { color: '#f0ece8', drawTicks: false },
      border: { dash: [4, 4] },
      ticks: {
        font: chartFont(),
        callback: isCurrency ? (v) => formatCAD(v) : undefined,
      },
      title: yLabel ? { display: true, text: yLabel, font: { ...chartFont(), size: 11 } } : {},
    },
  };
}

function commonTooltip(isCurrency = false) {
  return {
    callbacks: {
      label: (ctx) => {
        const v = ctx.parsed.y ?? ctx.parsed;
        return ` ${ctx.dataset.label || ''}: ${isCurrency ? formatCADFull(v) : formatNum(v)}`;
      },
    },
  };
}

/* ----------------------------------------------------------
   Small helper: build a simple Bar chart
   ---------------------------------------------------------- */
function buildBarChart(canvasId, labels, datasets, opts = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  destroyChart(canvasId);
  const chart = new Chart(canvas, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: datasets.length > 1 },
        tooltip: commonTooltip(opts.isCurrency),
      },
      scales: commonScales(opts.xLabel, opts.yLabel, opts.isCurrency),
      ...opts.extra,
    },
  });
  return registerChart(canvasId, chart);
}

function buildLineChart(canvasId, labels, datasets, opts = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  destroyChart(canvasId);
  const chart = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: datasets.length > 1 },
        tooltip: commonTooltip(opts.isCurrency),
      },
      scales: commonScales(opts.xLabel, opts.yLabel, opts.isCurrency),
      ...opts.extra,
    },
  });
  return registerChart(canvasId, chart);
}

function buildDoughnutChart(canvasId, labels, data, opts = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  destroyChart(canvasId);
  const chart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: PALETTE.map(c => c + 'DD'),
        borderWidth: 2,
        borderColor: '#fff',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { position: 'bottom', labels: { padding: 14, font: chartFont() } },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${opts.isCurrency ? formatCADFull(ctx.parsed) : formatNum(ctx.parsed)}`,
          },
        },
      },
      ...opts.extra,
    },
  });
  return registerChart(canvasId, chart);
}
