/**
 * analytics.js – Sales Insights page
 */
let _data = null;
let _activeMetric = 'revenue';

const METRICS = {
  revenue:      { field:'total_revenue',      label:'Revenue (CAD)', fmt: formatCAD,  currency:true  },
  quantity:     { field:'total_quantity',      label:'Quantity',      fmt: formatNum,  currency:false },
  transactions: { field:'unique_transactions', label:'Transactions',  fmt: formatNum,  currency:false },
};

document.addEventListener('DOMContentLoaded', async () => {
  try {
    _data = await getSalesInsights();
    populateFilters(_data);
    renderAll(_data);
  } catch (e) {
    ['monthly-chart', 'item-chart', 'prov-chart', 'payment-chart', 'loc-chart'].forEach(id =>
      showError(id, `Could not load data: ${e.message}`)
    );
  }
});

/* ----------------------------------------------------------
   Filters
   ---------------------------------------------------------- */
function populateFilters({ items, provinces, locations, paymentMethods }) {
  items.forEach(r          => document.getElementById('f-item')?.add(new Option(r.item,     r.item)));
  provinces.forEach(r      => document.getElementById('f-province')?.add(new Option(r.province, r.province)));
  locations.forEach(r      => document.getElementById('f-location')?.add(new Option(r.location, r.location)));
  paymentMethods.forEach(r => document.getElementById('f-payment')?.add(new Option(r.method,  r.method)));
}

function getFilters() {
  return {
    item:     document.getElementById('f-item')?.value     || '',
    province: document.getElementById('f-province')?.value || '',
    location: document.getElementById('f-location')?.value || '',
    payment:  document.getElementById('f-payment')?.value  || '',
  };
}

function applyFilters() {
  const f = getFilters();
  const hasFilter = Object.values(f).some(v => v !== '');
  document.getElementById('filter-badge').style.display = hasFilter ? 'inline-block' : 'none';
  renderAll({
    trends:         _data.trends,
    items:          f.item     ? _data.items.filter(r => r.item     === f.item)     : _data.items,
    provinces:      f.province ? _data.provinces.filter(r => r.province === f.province) : _data.provinces,
    locations:      f.location ? _data.locations.filter(r => r.location === f.location) : _data.locations,
    paymentMethods: f.payment  ? _data.paymentMethods.filter(r => r.method === f.payment) : _data.paymentMethods,
  });
}

function resetFilters() {
  ['f-item','f-province','f-location','f-payment'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('filter-badge').style.display = 'none';
  renderAll(_data);
}

/* ----------------------------------------------------------
   Metric selector
   ---------------------------------------------------------- */
function setMetric(metric) {
  _activeMetric = metric;
  ['revenue','quantity','transactions'].forEach(m => {
    const btn = document.getElementById(`btn-${m}`);
    if (btn) {
      btn.classList.toggle('active', m === metric);
      btn.setAttribute('aria-pressed', String(m === metric));
    }
  });
  applyFilters();
}

/* ----------------------------------------------------------
   Render all sections
   ---------------------------------------------------------- */
function renderAll(d) {
  renderMonthlyChart(d.trends);
  renderInsightCards(d);
  renderItemCharts(d.items);
  renderProvinceCharts(d.provinces);
  renderPaymentChart(d.paymentMethods);
  renderLocationChart(d.locations);
}

/* ----------------------------------------------------------
   Single monthly chart (driven by active metric)
   ---------------------------------------------------------- */
function renderMonthlyChart(trends) {
  if (!trends?.length) return;
  const m = METRICS[_activeMetric];
  document.getElementById('monthly-chart-title').textContent = `Monthly ${m.label} — 2023`;
  buildLineChart('monthly-chart', trends.map(r => r.month),
    [{ label: m.label, data: trends.map(r => r[m.field]), ...lineDefaults(COLORS.coffee) }],
    { isCurrency: m.currency, yLabel: m.label });
}

/* ----------------------------------------------------------
   Insight cards (3 max)
   ---------------------------------------------------------- */
function renderInsightCards(d) {
  if (!d.items?.length || !d.provinces?.length || !d.trends?.length) return;
  const topItem  = d.items[0];
  const topProv  = d.provinces[0];
  const lastMo   = d.trends[d.trends.length - 1];
  const firstMo  = d.trends[0];
  const revDelta = ((lastMo.total_revenue - firstMo.total_revenue) / firstMo.total_revenue * 100).toFixed(1);

  const cards = [
    {
      finding: `${topItem.item} leads by revenue`,
      metric:  `${formatCAD(topItem.total_revenue)} · ${formatNum(topItem.unique_transactions)} transactions`,
      meaning: `${topItem.item} is the strongest revenue driver. Bundle or upsell opportunities should be explored.`,
    },
    {
      finding: `${topProv.province} is the top market`,
      metric:  `${formatCAD(topProv.total_revenue)} · ${formatNum(topProv.unique_transactions)} transactions`,
      meaning: `${topProv.province} outperforms all other provinces. Regional marketing investment here is likely to yield the highest return.`,
    },
    {
      finding: `Revenue ${revDelta >= 0 ? '+' : ''}${revDelta}% from ${firstMo.month} to ${lastMo.month}`,
      metric:  `${formatCAD(firstMo.total_revenue)} → ${formatCAD(lastMo.total_revenue)}`,
      meaning: revDelta >= 0
        ? 'Revenue grew over 2023. Sustaining this trend into 2024 is the primary goal.'
        : 'Revenue declined from start to end of 2023. Investigate seasonal factors and promotional timing.',
    },
  ];

  document.getElementById('insight-cards-row').innerHTML = cards.map(c => `
    <div class="col-md-4">
      <div class="insight-finding-card h-100">
        <div class="if-finding">${c.finding}</div>
        <div class="if-metric"><i class="bi bi-graph-up me-1" aria-hidden="true"></i>${c.metric}</div>
        <div class="if-meaning">${c.meaning}</div>
      </div>
    </div>`).join('');
}

/* ----------------------------------------------------------
   Item table only
   ---------------------------------------------------------- */
function renderItemCharts(items) {
  if (!items?.length) return;
  const m = METRICS[_activeMetric];
  const sorted = [...items].sort((a, b) => b[m.field] - a[m.field]);
  document.getElementById('item-tbody').innerHTML = sorted.map((r, i) => `
    <tr>
      <td><span class="rank-badge">${i + 1}</span></td>
      <td>${r.item}</td>
      <td>${formatCAD(r.total_revenue)}</td>
      <td>${formatNum(r.total_quantity)}</td>
      <td>${formatNum(r.unique_transactions)}</td>
    </tr>`).join('');
}

/* ----------------------------------------------------------
   Province chart – vertical bars, single colour
   ---------------------------------------------------------- */
function renderProvinceCharts(provinces) {
  if (!provinces?.length) return;
  const m = METRICS[_activeMetric];
  const sorted = [...provinces].sort((a, b) => b[m.field] - a[m.field]);
  document.getElementById('prov-chart-title').textContent = `${m.label} by Province`;
  buildBarChart('prov-chart', sorted.map(r => r.province),
    [{ label: m.label, data: sorted.map(r => r[m.field]),
       backgroundColor: COLORS.amber + 'CC', borderRadius: 4 }],
    { isCurrency: m.currency, yLabel: m.label });

  document.getElementById('prov-tbody').innerHTML = sorted.map((r, i) => `
    <tr>
      <td><span class="rank-badge">${i + 1}</span></td>
      <td>${r.province}</td>
      <td>${formatCAD(r.total_revenue)}</td>
      <td>${formatNum(r.total_quantity)}</td>
    </tr>`).join('');
}

/* ----------------------------------------------------------
   Payment chart – compact horizontal bar (≤ 300 px)
   ---------------------------------------------------------- */
function renderPaymentChart(methods) {
  if (!methods?.length) { showEmpty('payment-chart', 'No payment data.'); return; }
  buildBarChart('payment-chart', methods.map(r => r.method),
    [{ label: 'Transactions', data: methods.map(r => r.count),
       backgroundColor: COLORS.coffee + 'CC', borderRadius: 4 }],
    {
      extra: {
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` Transactions: ${formatNum(ctx.parsed.x)}` } },
        },
        scales: {
          x: { grid: { color: '#f0ece8' }, ticks: { font: chartFont() } },
          y: { grid: { display: false }, ticks: { font: chartFont() } },
        },
      },
    });
}

/* ----------------------------------------------------------
   Location chart – compact horizontal bar (≤ 160 px)
   ---------------------------------------------------------- */
function renderLocationChart(locations) {
  if (!locations?.length) { showEmpty('loc-chart', 'No location data.'); return; }
  buildBarChart('loc-chart', locations.map(r => r.location),
    [{ label: 'Revenue', data: locations.map(r => r.total_revenue),
       backgroundColor: COLORS.teal + 'CC', borderRadius: 4 }],
    {
      extra: {
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` Revenue: ${formatCADFull(ctx.parsed.x)}` } },
        },
        scales: {
          x: {
            grid: { color: '#f0ece8' },
            ticks: { font: chartFont(), callback: v => formatCAD(v) },
          },
          y: { grid: { display: false }, ticks: { font: chartFont() } },
        },
      },
    });
}
